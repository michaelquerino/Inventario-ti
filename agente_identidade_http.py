"""Servidor HTTP local (127.0.0.1) que devolve a identidade deste notebook
(numero_serie e, quando disponível, usuário/patrimônio) para a página de
abertura de chamados no navegador do próprio usuário conseguir se identificar
sozinha, sem pedir login. Só escuta em loopback -- nenhum outro computador da
rede consegue alcançar essa porta, só processos rodando nesta mesma máquina
(inclusive o navegador do usuário logado nela).
"""

import http.server
import json
import logging
import re
import threading

logger = logging.getLogger(__name__)

PORTA_IDENTIDADE = 18763

# Mesmo padrão do cors_origin_regex do backend (backend/app/core/config.py):
# LAN, Tailscale (CGNAT 100.64.0.0/10) e o nome amigável "infradesk", todos na
# porta 3000 do frontend. Sem isso, qualquer site aberto no navegador do
# usuário poderia varrer localhost e ler o número de série da máquina.
_ORIGEM_PERMITIDA_RE = re.compile(
    r"^https?://(192\.168\.\d{1,3}\.\d{1,3}"
    r"|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}"
    r"|infradesk):3000$"
)


def iniciar_servidor_identidade(numero_serie_fn, vinculo_fn=None):
    """Inicia o servidor em uma thread daemon e retorna imediatamente.
    numero_serie_fn: callable sem argumentos -> str | None
    vinculo_fn: callable sem argumentos -> dict com usuario/patrimonio/patrimonio_monitor, ou None
    """

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format_str, *args):
            pass  # não polui o log do agente com cada requisição

        def _origem_permitida(self):
            origem = self.headers.get("Origin", "")
            return origem if _ORIGEM_PERMITIDA_RE.match(origem) else None

        def do_OPTIONS(self):
            origem = self._origem_permitida()
            self.send_response(204)
            if origem:
                self.send_header("Access-Control-Allow-Origin", origem)
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            if self.path.split("?", 1)[0].rstrip("/") != "/identidade":
                self.send_response(404)
                self.end_headers()
                return

            vinculo = (vinculo_fn() if vinculo_fn else None) or {}
            corpo = json.dumps(
                {
                    "numero_serie": numero_serie_fn(),
                    "usuario": vinculo.get("usuario") or None,
                    "patrimonio": vinculo.get("patrimonio") or None,
                    "patrimonio_monitor": vinculo.get("patrimonio_monitor") or None,
                }
            ).encode("utf-8")

            origem = self._origem_permitida()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            if origem:
                self.send_header("Access-Control-Allow-Origin", origem)
            self.end_headers()
            self.wfile.write(corpo)

    try:
        servidor = http.server.HTTPServer(("127.0.0.1", PORTA_IDENTIDADE), Handler)
    except OSError as erro:
        logger.warning(
            "Não foi possível iniciar o servidor local de identidade em 127.0.0.1:%s (%s) -- "
            "provavelmente já há outra instância do agente rodando.",
            PORTA_IDENTIDADE,
            erro,
        )
        return None

    thread = threading.Thread(target=servidor.serve_forever, daemon=True, name="identidade-http")
    thread.start()
    logger.info("Servidor local de identidade escutando em 127.0.0.1:%s", PORTA_IDENTIDADE)
    return servidor
