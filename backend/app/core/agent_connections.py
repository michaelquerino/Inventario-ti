"""Registro em memória das conexões WebSocket ativas dos agentes (numero_serie
-> conexão). A conexão aberta É o sinal de "online" -- não depende mais de
esperar horas de silêncio pra concluir que um agente caiu, e permite empurrar
comandos pro agente na hora em vez de esperar o próximo ciclo de consulta."""

import asyncio
import logging
import time
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class AgentConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._last_seen: dict[str, float] = {}
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Chamado uma vez no startup do FastAPI -- guarda o event loop
        principal pra permitir agendar envios a partir de rotas síncronas
        comuns, que o FastAPI roda numa threadpool fora desse loop."""
        self._main_loop = loop

    async def connect(self, numero_serie: str, websocket: WebSocket) -> None:
        existente = self._connections.get(numero_serie)
        if existente is not None and existente is not websocket:
            # Mesmo notebook abrindo uma segunda conexão (ex: reconexão rápida
            # antes do servidor perceber que a antiga caiu) -- fecha a velha
            # pra não ficar com duas registradas pro mesmo numero_serie.
            try:
                await existente.close(code=4000, reason="Substituída por nova conexão")
            except Exception:
                pass
        self._connections[numero_serie] = websocket
        self._last_seen[numero_serie] = time.monotonic()

    def disconnect(self, numero_serie: str, websocket: WebSocket) -> None:
        if self._connections.get(numero_serie) is websocket:
            self._connections.pop(numero_serie, None)
            self._last_seen.pop(numero_serie, None)

    def mark_seen(self, numero_serie: str) -> None:
        """Chamado a cada mensagem recebida de um agente (heartbeat ou não) --
        é a prova de vida que a faxina de conexões zumbis usa pra decidir o
        que ainda está realmente conectado."""
        if numero_serie in self._connections:
            self._last_seen[numero_serie] = time.monotonic()

    def is_online(self, numero_serie: str) -> bool:
        return numero_serie in self._connections

    def online_serials(self) -> set[str]:
        return set(self._connections.keys())

    async def reap_stale(self, max_idle_seconds: float) -> list[str]:
        """Fecha e remove conexões sem nenhuma mensagem há mais de
        max_idle_seconds. Cobre o caso de a conexão TCP cair sem um close
        limpo chegar ao servidor (ex: notebook saiu da rede, troca de rede no
        Tailscale) -- sem isso, a conexão fica marcada 'online' indefinidamente
        e comandos empurrados pra ela somem em silêncio."""
        agora = time.monotonic()
        mortas = [
            serie
            for serie, visto in list(self._last_seen.items())
            if agora - visto > max_idle_seconds
        ]
        for serie in mortas:
            websocket = self._connections.pop(serie, None)
            self._last_seen.pop(serie, None)
            if websocket is not None:
                try:
                    await websocket.close(code=4008, reason="Sem atividade")
                except Exception:
                    pass
        return mortas

    async def send_json(self, numero_serie: str, message: dict) -> bool:
        websocket = self._connections.get(numero_serie)
        if websocket is None:
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            logger.warning("Falha ao enviar mensagem pro agente %s", numero_serie)
            return False

    def notify_threadsafe(self, numero_serie: str, message: dict) -> None:
        """Agenda o envio a partir de código síncrono (ex: a rota REST de criar
        comando, que roda numa threadpool). Não garante entrega -- se o agente
        não estiver conectado agora, a mensagem é só descartada; o comando
        continua 'pendente' no banco e será entregue no próximo handshake."""
        if self._main_loop is None:
            return
        asyncio.run_coroutine_threadsafe(self.send_json(numero_serie, message), self._main_loop)


agent_connections = AgentConnectionManager()
