"""Canal WebSocket usado pelos agentes (notebooks) pra falar com o servidor:
substitui o polling HTTP antigo (que ainda existe em servidor.py/porta 5000,
intacto, pros agentes que ainda não migraram) por uma conexão persistente --
comando chega na hora, e o servidor sabe em tempo real se o notebook está
online (a conexão aberta É o sinal, sem precisar esperar silêncio de horas).

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
import sys
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
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
