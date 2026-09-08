"""Cliente WebSocket compartilhado por agente.py e agente_manual.py.

Substitui o polling HTTP antigo por uma conexão persistente com o backend:
comando chega na hora (empurrado pelo servidor) em vez de esperar até 1
minuto, e o servidor sabe em tempo real se o notebook está online (a conexão
aberta é o sinal -- sem precisar esperar silêncio de horas pra concluir que
caiu).

A resiliência pedida -- "não posso correr o risco de ficar sem conexão" --
vem de duas partes:
  1. Reconexão automática com backoff, pra sempre (nunca desiste de vez),
     cobrindo queda de wifi, notebook suspenso, servidor reiniciando, etc.
  2. Qualquer mensagem que falhe ao enviar (por estar desconectado no
     momento) é guardada em disco e reenviada assim que a conexão voltar --
     nada se perde por causa de uma queda temporária.
"""

import json
import logging
import os
import threading
import time

import websocket  # pacote "websocket-client"

logger = logging.getLogger(__name__)

_RECONEXAO_MIN_SEGUNDOS = 2
_RECONEXAO_MAX_SEGUNDOS = 60
_HEARTBEAT_INTERVALO_SEGUNDOS = 20


class ClienteAgenteWS:
    def __init__(self, enderecos, porta, api_key, numero_serie_fn, on_command, caminho_fila, fila_max_itens=500):
        """
        enderecos: lista de IPs do backend (tenta cada um em sequência a cada
            nova tentativa de conexão, igual ao polling antigo fazia).
        porta: porta do backend FastAPI que hospeda o endpoint /ws/agent.
        api_key: mesma chave de API usada pelo polling antigo (X-API-Key).
        numero_serie_fn: função que retorna o numero_serie atual (pode ainda
            não estar disponível no primeiríssimo instante).
        on_command: callback(comando_id, comando_texto, modo) chamado numa
            THREAD SEPARADA a cada comando recebido, pra não travar a conexão
            enquanto o comando roda (pode levar até alguns minutos).
        caminho_fila: arquivo onde mensagens não entregues ficam guardadas
            até a próxima reconexão.
        """
        self._enderecos = [str(ip).strip() for ip in (enderecos or []) if str(ip).strip()]
        self._porta = porta
        self._api_key = api_key
        self._numero_serie_fn = numero_serie_fn
        self._on_command = on_command
        self._caminho_fila = caminho_fila
        self._fila_max_itens = fila_max_itens

        self._ws = None
        self._lock = threading.Lock()
        self._parar = threading.Event()
        self._conectado = threading.Event()
        self._atraso_reconexao = _RECONEXAO_MIN_SEGUNDOS
        self._indice_endereco = 0

    def iniciar(self):
        thread = threading.Thread(target=self._loop_reconexao, daemon=True, name="agente-ws")
        thread.start()
        threading.Thread(target=self._loop_heartbeat, daemon=True, name="agente-ws-heartbeat").start()
        return thread

    def _loop_heartbeat(self):
        """Manda um heartbeat de aplicação periodicamente enquanto conectado.
        O servidor usa isso (junto com qualquer outra mensagem) como prova de
        vida pra detectar conexões que caíram sem um close limpo (ex: troca de
        rede no Tailscale) e evitar ficar marcado 'online' pra sempre sem
        receber comando nenhum."""
        while not self._parar.wait(_HEARTBEAT_INTERVALO_SEGUNDOS):
            if self._conectado.is_set():
                self.enviar({"type": "heartbeat"})

    def parar(self):
        self._parar.set()
        with self._lock:
            ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def esta_conectado(self):
        return self._conectado.is_set()

    def enviar(self, mensagem: dict) -> bool:
        """Tenta enviar agora. Retorna False sem lançar exceção se não der
        (desconectado ou qualquer falha de rede)."""
        with self._lock:
            ws = self._ws
        if ws is None or not self._conectado.is_set():
            return False
        try:
            ws.send(json.dumps(mensagem, ensure_ascii=False))
            return True
        except Exception as erro:
            logger.warning("Falha ao enviar mensagem pelo WebSocket: %s", erro)
            return False

    def enviar_ou_enfileirar(self, mensagem: dict) -> None:
        """Tenta enviar; se não conseguir, guarda em disco pra reenviar assim
        que a conexão voltar. Usado tanto pro relatório de monitoramento
        periódico quanto pra início/resultado de comandos."""
        if self.enviar(mensagem):
            return
        self._enfileirar(mensagem)

    # --- fila local (persistida em disco) ---------------------------------

    def _carregar_fila(self):
        if not os.path.exists(self._caminho_fila):
            return []
        try:
            with open(self._caminho_fila, "r", encoding="utf-8") as arquivo:
                conteudo = json.load(arquivo)
            return conteudo if isinstance(conteudo, list) else []
        except (OSError, json.JSONDecodeError) as erro:
            logger.error("Falha ao ler fila local de mensagens: %s", erro)
            return []

    def _salvar_fila(self, itens):
        try:
            with open(self._caminho_fila, "w", encoding="utf-8") as arquivo:
                json.dump(itens, arquivo, ensure_ascii=False)
        except OSError as erro:
            logger.error("Falha ao salvar fila local de mensagens: %s", erro)

    def _enfileirar(self, mensagem):
        fila = self._carregar_fila()
        fila.append(mensagem)
        if len(fila) > self._fila_max_itens:
            excesso = len(fila) - self._fila_max_itens
            fila = fila[excesso:]
            logger.warning("Fila local de mensagens excedeu limite; %s item(ns) mais antigo(s) removido(s).", excesso)
        self._salvar_fila(fila)
        logger.info("Mensagem enfileirada localmente (sem conexão). Pendentes: %s", len(fila))

    def _flush_fila(self):
        fila = self._carregar_fila()
        if not fila:
            return
        logger.info("Reenviando %s mensagem(ns) da fila local após reconexão...", len(fila))
        restantes = []
        falhou = False
        for mensagem in fila:
            if falhou or not self.enviar(mensagem):
                falhou = True
                restantes.append(mensagem)
        self._salvar_fila(restantes)
        if not restantes:
            logger.info("Fila local de mensagens sincronizada com sucesso.")

    # --- conexão / reconexão -----------------------------------------------

    def _proximo_endereco(self):
        if not self._enderecos:
            return None
        ip = self._enderecos[self._indice_endereco % len(self._enderecos)]
        self._indice_endereco += 1
        return ip

    def _loop_reconexao(self):
        while not self._parar.is_set():
            numero_serie = (self._numero_serie_fn() or "").strip()
            if not numero_serie:
                time.sleep(2)
                continue

            ip = self._proximo_endereco()
            if not ip:
                logger.error("Nenhum endereço de servidor configurado; tentando novamente em %ss", self._atraso_reconexao)
                time.sleep(self._atraso_reconexao)
                continue

            url = f"ws://{ip}:{self._porta}/ws/agent?numero_serie={numero_serie}"
            logger.info("Conectando ao servidor via WebSocket: %s", url)

            ws = websocket.WebSocketApp(
                url,
                header=[f"X-API-Key: {self._api_key}"],
                on_open=self._on_open,
                on_message=self._on_message,
                on_close=self._on_close,
                on_error=self._on_error,
            )
            with self._lock:
                self._ws = ws

            try:
                # ping_interval/ping_timeout mantêm a conexão viva e detectam
                # quedas silenciosas (wifi trocado, notebook suspenso sem
                # fechar a conexão direito) -- só retorna quando a conexão cai.
                ws.run_forever(ping_interval=25, ping_timeout=10)
            except Exception as erro:
                logger.warning("Erro na conexão WebSocket: %s", erro)

            self._conectado.clear()
            with self._lock:
                self._ws = None

            if self._parar.is_set():
                return

            logger.info("Conexão WebSocket caiu; tentando de novo em %ss", self._atraso_reconexao)
            time.sleep(self._atraso_reconexao)
            self._atraso_reconexao = min(self._atraso_reconexao * 2, _RECONEXAO_MAX_SEGUNDOS)

    def _on_open(self, ws):
        logger.info("Conectado ao servidor via WebSocket.")
        self._conectado.set()
        self._atraso_reconexao = _RECONEXAO_MIN_SEGUNDOS
        self._flush_fila()

    def _on_message(self, ws, mensagem_texto):
        try:
            mensagem = json.loads(mensagem_texto)
        except (TypeError, ValueError):
            return

        tipo = mensagem.get("type")
        if tipo == "command":
            comando_id = mensagem.get("id")
            comando_texto = mensagem.get("comando")
            modo = mensagem.get("modo") or "usuario"
            if comando_id is None or not comando_texto:
                return
            threading.Thread(
                target=self._on_command,
                args=(comando_id, comando_texto, modo),
                daemon=True,
                name=f"comando-{comando_id}",
            ).start()

    def _on_close(self, ws, codigo, motivo):
        logger.info("Conexão WebSocket encerrada (código=%s, motivo=%s)", codigo, motivo)
        self._conectado.clear()

    def _on_error(self, ws, erro):
        logger.warning("Erro no WebSocket: %s", erro)
