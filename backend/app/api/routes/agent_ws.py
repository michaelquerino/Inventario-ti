"""Canal WebSocket usado pelos agentes (notebooks) pra falar com o servidor:
substitui o polling HTTP antigo (servidor.py/Flask, porta 5000) por uma
conexão persistente -- comando chega na hora, e o servidor sabe em tempo
real se o notebook está online (a conexão aberta É o sinal, sem precisar
esperar silêncio de horas). Nenhum build atual do agente (agente.py ou
agente_manual.py) chama mais os endpoints HTTP antigos -- os dois só usam
este canal WebSocket pra reportar e receber comandos.

Este módulo também serve GET /agente/download (mesmo caminho que existia em
servidor.py), usado pelo script de autoatualização remota (veja
api/routes/commands.py::_build_agent_update_script) -- é a única coisa que
ainda dependia do Flask depois da migração pra WebSocket.

Protocolo (mensagens JSON, um por linha via WebSocket):

Agente -> servidor:
  {"type": "monitoring", "data": {...mesmos campos do antigo POST /reportar...}}
  {"type": "command_started", "id": <int>}
  {"type": "command_result", "id": <int>, "sucesso": bool, "codigo_saida": int|null, "resultado": str}
  {"type": "heartbeat"}

Servidor -> agente:
  {"type": "command", "id": <int>, "comando": str, "modo": "usuario"|"admin"}
  {"type": "pong"}
"""

import logging
import os
import sys
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.core.agent_connections import agent_connections
from app.core.config import settings
from app.core.legacy_db import repo_root as _repo_root

logger = logging.getLogger(__name__)
router = APIRouter()


def _load_root_database():
    repo_root = str(_repo_root())
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    import database  # database.py na raiz do repositório (mesmo usado pelo servidor.py Flask)

    return database


def _load_root_config():
    repo_root = str(_repo_root())
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    import config  # config.py na raiz do repositório (usado pelo agente/servidor)

    return config


# Equivalente ao antigo GET /agente/download em servidor.py (Flask, porta
# 5000) -- migrado pra cá pra não depender mais do Flask rodando só pra
# servir esse arquivo. Mesmo caminho e mesma autenticação por X-API-Key,
# só a porta muda no script que baixa isso (veja
# api/routes/commands.py::_build_agent_update_script).
@router.get("/agente/download")
def agente_download(request: Request) -> FileResponse:
    api_key = request.headers.get("x-api-key")
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key inválida")

    cfg = _load_root_config()
    caminho = getattr(cfg, "AGENTE_EXE_PATH", None)
    if not caminho or not os.path.isfile(caminho):
        logger.warning("Download de agente solicitado, mas executável não encontrado em %s", caminho)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Executável do agente não encontrado no servidor")

    return FileResponse(caminho, media_type="application/octet-stream", filename="Agente_manual.exe")


@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket) -> None:
    api_key = websocket.headers.get("x-api-key")
    numero_serie = (websocket.query_params.get("numero_serie") or "").strip()

    await websocket.accept()

    if not api_key or api_key != settings.agent_api_key:
        logger.warning("Conexão WS de agente recusada: API key inválida (numero_serie=%r)", numero_serie)
        await websocket.close(code=4401, reason="API key inválida")
        return

    if not numero_serie:
        await websocket.close(code=4400, reason="numero_serie obrigatório")
        return

    database = _load_root_database()

    await agent_connections.connect(numero_serie, websocket)
    logger.info("Agente conectado via WebSocket: %s", numero_serie)

    try:
        # Entrega imediatamente qualquer comando que já estava esperando --
        # nada fica "perdido" enquanto o agente estava desconectado, porque
        # ele continua marcado 'pendente' no banco até ser mesmo executado.
        pendentes = await run_in_threadpool(database.listar_comandos_pendentes, numero_serie)
        for comando_id, comando_texto, modo in pendentes:
            await websocket.send_json(
                {"type": "command", "id": comando_id, "comando": comando_texto, "modo": modo or "usuario"}
            )

        while True:
            mensagem = await websocket.receive_json()
            agent_connections.mark_seen(numero_serie)
            tipo = mensagem.get("type")

            if tipo == "heartbeat":
                await websocket.send_json({"type": "pong"})

            elif tipo == "monitoring":
                dados = mensagem.get("data") or {}
                dados["ultima_atualizacao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await run_in_threadpool(database.salvar_monitoramento, dados)

            elif tipo == "command_started":
                comando_id = mensagem.get("id")
                if comando_id is not None:
                    await run_in_threadpool(database.marcar_comando_executando, comando_id)

            elif tipo == "command_result":
                comando_id = mensagem.get("id")
                if comando_id is not None:
                    await run_in_threadpool(
                        database.salvar_resultado_comando,
                        comando_id,
                        bool(mensagem.get("sucesso")),
                        mensagem.get("codigo_saida"),
                        str(mensagem.get("resultado") or "")[:20000],
                    )

            else:
                logger.debug("Mensagem WS de tipo desconhecido de %s: %r", numero_serie, tipo)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Erro na conexão WS do agente %s", numero_serie)
    finally:
        agent_connections.disconnect(numero_serie, websocket)
        logger.info("Agente desconectado do WebSocket: %s", numero_serie)
