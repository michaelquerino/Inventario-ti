import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from sqlalchemy import text

import app.models  # noqa: F401
import app.models.backup_log  # noqa: F401 -- registra BackupLog no BackupBase (banco separado)
from app.api.router import api_router
from app.api.routes.agent_ws import router as agent_ws_router
from app.core.agent_connections import agent_connections
from app.core.config import settings
from app.core.rate_limit import limiter
from app.crud import backup as backup_crud
from app.crud.user import create_user, enforce_single_admin, get_by_email
from app.db.backup_session import BackupBase, backup_engine
from app.db.session import Base, SessionLocal, engine
from app.schemas.user import UserCreate

logger = logging.getLogger(__name__)

# O heartbeat de ~20s (agente_ws_client.py) só existe nos agentes já
# atualizados com essa versão; boa parte da frota ainda roda o .exe antigo,
# que só manda mensagem a cada INTERVALO_HORAS=0.5h (config.py) e fica mudo
# entre um relatório e outro. Por isso o limite aqui precisa ser folgado o
# bastante pra nunca derrubar um agente antigo saudável no meio do ciclo --
# 40 min ainda corrige o bug real (conexão morta que ficava "online" pra
# sempre) sem gerar falso positivo. Depois que o rollout do heartbeat cobrir
# toda a frota, dá pra apertar esse valor pra algo bem mais rápido (ex: 90s).
AGENT_WS_REAPER_INTERVAL_SECONDS = 60
AGENT_WS_MAX_IDLE_SECONDS = 2400


def _run_lightweight_migrations() -> None:
    """create_all só cria tabelas novas; colunas adicionadas depois a uma tabela
    já existente precisam de ALTER TABLE manual (não há Alembic neste projeto)."""
    with engine.begin() as connection:
        existing_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(assets)")).fetchall()
        }
        if "screen_asset_tag" not in existing_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN screen_asset_tag VARCHAR(64)"))


async def _reaper_conexoes_zumbis() -> None:
    """Roda em segundo plano durante toda a vida do processo: fecha e remove
    conexões de agente sem nenhuma mensagem (nem heartbeat) há mais de
    AGENT_WS_MAX_IDLE_SECONDS. Sem isso, uma conexão que morre sem um close
    limpo (wifi trocado, notebook hibernou, queda de túnel Tailscale) fica
    marcada 'online' pra sempre e comandos empurrados pra ela somem em
    silêncio -- só voltam a ser entregues no próximo reconexão real do
    agente."""
    while True:
        try:
            await asyncio.sleep(AGENT_WS_REAPER_INTERVAL_SECONDS)
            mortas = await agent_connections.reap_stale(AGENT_WS_MAX_IDLE_SECONDS)
            if mortas:
                logger.warning("Conexões de agente sem atividade removidas: %s", mortas)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha na faxina de conexões zumbis de agente")


async def _executar_backup_periodico() -> None:
    """Roda em segundo plano durante toda a vida do processo: aguarda um
    intervalo configurável (settings.backup_interval_hours) e dispara um
    backup automático dos bancos, repetindo indefinidamente."""
    intervalo_segundos = max(settings.backup_interval_hours, 0.1) * 3600
    while True:
        try:
            await asyncio.sleep(intervalo_segundos)
            backup_crud.run_backup(
                triggered_by="agendado",
                retention_count=settings.backup_retention_count,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha ao executar backup agendado")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    # Adicionar middleware de rate limiting
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    # Fora do prefixo versionado/JWT: agentes autenticam com X-API-Key própria
    # (mesma chave do polling antigo em servidor.py), não com token de usuário.
    app.include_router(agent_ws_router)

    @app.middleware("http")
    async def set_api_version_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-API-Version"] = settings.api_version
        return response

    @app.on_event("startup")
    def on_startup() -> None:
        agent_connections.bind_loop(asyncio.get_running_loop())
        Base.metadata.create_all(bind=engine)
        BackupBase.metadata.create_all(bind=backup_engine)
        _run_lightweight_migrations()
        if settings.admin_email and settings.admin_password:
            db = SessionLocal()
            try:
                if get_by_email(db, settings.admin_email) is None:
                    create_user(
                        db,
                        UserCreate(
                            email=settings.admin_email,
                            full_name=settings.admin_full_name,
                            role="admin",
                            password=settings.admin_password,
                        ),
                    )
                if settings.single_admin_mode:
                    enforce_single_admin(db, settings.admin_email)
            finally:
                db.close()

        asyncio.create_task(_executar_backup_periodico())
        asyncio.create_task(_reaper_conexoes_zumbis())

    return app


app = create_app()
