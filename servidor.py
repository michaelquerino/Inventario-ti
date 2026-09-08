"""
Servidor que recebe os relatórios de monitoramento enviados pelos agentes
instalados nos notebooks dos funcionários.
"""
import logging
import os
import subprocess
import sys
from flask import Flask, request, jsonify, send_file
from functools import wraps
import database
import config
from datetime import datetime
import secrets

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('servidor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Chave de API para autenticação dos agentes
API_KEY = secrets.token_urlsafe(32) if not hasattr(config, 'API_KEY_SERVIDOR') else config.API_KEY_SERVIDOR

def requer_autenticacao(f):
    """Decorador para validar API key nas requisições."""
    @wraps(f)
    def decorado(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != API_KEY:
            logger.warning(f"Tentativa de acesso não autorizado de {request.remote_addr}")
            return jsonify({"erro": "Não autorizado"}), 401
        return f(*args, **kwargs)
    return decorado

def validar_payload(dados):
    """Valida tipos e tamanhos do payload antes de gravar."""
    campos_obrigatorios = ["numero_serie", "modelo", "sistema_operacional"]
    campos_numericos = ["disco_total_gb", "disco_usado_gb", "disco_livre_gb",
                        "uso_cpu_percentual", "uso_memoria_percentual", "uso_disco_percentual",
                        "rede_enviado_mb", "rede_recebido_mb", "fila_pendente_local"]
    
    # Valida campos obrigatórios
    for campo in campos_obrigatorios:
        if campo not in dados or not str(dados[campo]).strip():
            return False, f"Campo obrigatório '{campo}' não informado"
    
    # Valida campos numéricos
    for campo in campos_numericos:
        if campo in dados:
            try:
                float(dados[campo])
            except (TypeError, ValueError):
                return False, f"Campo '{campo}' deve ser numérico"
    
    # Limita tamanho de strings
    for campo in ["numero_serie", "modelo"]:
        if len(str(dados.get(campo, ""))) > 255:
            return False, f"Campo '{campo}' excede tamanho máximo"
    
    return True, None


@app.route("/reportar", methods=["POST"])
@requer_autenticacao
def reportar():
    """Recebe um relatório de monitoramento em JSON e salva no banco de dados."""
    try:
        dados = request.get_json()
        
        if not dados:
            logger.warning(f"Payload vazio de {request.remote_addr}")
            return jsonify({"erro": "Payload inválido"}), 400
        
        # Valida o payload
        valido, erro = validar_payload(dados)
        if not valido:
            logger.warning(f"Payload inválido de {request.remote_addr}: {erro}")
            return jsonify({"erro": erro}), 400
        
        dados["ultima_atualizacao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        database.salvar_monitoramento(dados)
        
        logger.info(f"Relatório recebido de: {dados.get('numero_serie')} ({dados.get('modelo')})")
        return jsonify({"status": "ok"}), 200
    
    except Exception as e:
        logger.error(f"Erro ao processar relatório: {str(e)}", exc_info=True)
        return jsonify({"erro": "Erro interno do servidor"}), 500



@app.route("/comandos", methods=["GET"])
@requer_autenticacao
def comandos_pendentes():
    """Retorna os comandos pendentes de um notebook, para o agente buscar no checkin."""
    numero_serie = (request.args.get("numero_serie") or "").strip()
    if not numero_serie:
        return jsonify({"erro": "Parâmetro 'numero_serie' obrigatório"}), 400

    pendentes = database.listar_comandos_pendentes(numero_serie)
    return jsonify(
        [{"id": comando_id, "comando": comando, "modo": modo or "usuario"} for comando_id, comando, modo in pendentes]
    ), 200


@app.route("/comandos/<int:comando_id>/iniciar", methods=["POST"])
@requer_autenticacao
def comandos_iniciar(comando_id):
    """Marca um comando como em execução, para não ser buscado de novo no próximo checkin."""
    database.marcar_comando_executando(comando_id)
    return jsonify({"status": "ok"}), 200


@app.route("/comandos/<int:comando_id>/resultado", methods=["POST"])
@requer_autenticacao
def comandos_resultado(comando_id):
    """Recebe o resultado de execução de um comando enviado pelo agente."""
    dados = request.get_json(silent=True) or {}

    sucesso = bool(dados.get("sucesso"))
    codigo_saida = dados.get("codigo_saida")
    resultado = str(dados.get("resultado") or "")[:20000]

    try:
        codigo_saida = int(codigo_saida) if codigo_saida is not None else None
    except (TypeError, ValueError):
        codigo_saida = None

    database.salvar_resultado_comando(comando_id, sucesso, codigo_saida, resultado)
    logger.info("Resultado do comando %s recebido (sucesso=%s)", comando_id, sucesso)
    return jsonify({"status": "ok"}), 200


@app.route("/agente/download", methods=["GET"])
@requer_autenticacao
def agente_download():
    """Serve o executável mais recente do agente, para autoatualização remota via comando."""
    caminho = getattr(config, "AGENTE_EXE_PATH", None)
    if not caminho or not os.path.isfile(caminho):
        logger.warning("Download de agente solicitado, mas executável não encontrado em %s", caminho)
        return jsonify({"erro": "Executável do agente não encontrado no servidor"}), 404

    return send_file(caminho, as_attachment=True, download_name="Agente_manual.exe")


def iniciar_servidor():
    """Inicia o servidor Flask, escutando em todas as interfaces de rede na porta 5000."""
    logger.info(f"Iniciando servidor com API_KEY (primeiros 8 chars): {API_KEY[:8]}...")
    try:
        subprocess.run(
            [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                "name=InventarioTI-5000",
                "dir=in",
                "action=allow",
                "protocol=TCP",
                "localport=5000",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as erro:
        logger.warning("Falha ao ajustar regra de firewall: %s", erro)

    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    database.criar_tabela_monitoramento()
    database.criar_tabela_comandos()
    logger.info("Tabelas do banco de dados inicializadas")
    iniciar_servidor()