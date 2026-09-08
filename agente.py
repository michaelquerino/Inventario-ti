"""
Agente de monitoramento — roda no notebook do funcionário e reporta
o estado da máquina para o servidor central de inventário.
"""

import platform
import shutil
import psutil
import subprocess
import time
import config
import logging
import os
import sys
import json
import uuid
from datetime import datetime

import agente_identidade_http
import agente_ws_client


def caminho_log():
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    pasta = os.path.join(base, "InventarioTI", "logs")
    if not os.path.exists(pasta):
        os.makedirs(pasta)
    return os.path.join(pasta, "agente.log")


def caminho_instalacao():
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    pasta = os.path.join(base, "InventarioTI")
    if not os.path.exists(pasta):
        os.makedirs(pasta)
    return os.path.join(pasta, "AgenteInventario.exe")


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(caminho_log(), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

ENDERECOS_SERVIDOR = getattr(
    config,
    "ENDERECOS_SERVIDOR",
    [config.IP_SERVIDOR_PRINCIPAL, config.IP_SERVIDOR_VPN],
)

# Chave de API para autenticação no servidor
API_KEY = getattr(config, 'API_KEY_AGENTE', 'chave-padrao-alterar')
NOME_TAREFA = "InventarioTI - Agente"
FILA_MAX_ITENS = getattr(config, "FILA_MAX_ITENS", 500)


def caminho_fila_local():
    """Arquivo onde mensagens (relatórios de monitoramento, início/resultado
    de comando) ficam guardadas quando não há conexão WebSocket ativa no
    momento do envio, até serem reenviadas na próxima reconexão."""
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    pasta = os.path.join(base, "InventarioTI", "queue")
    if not os.path.exists(pasta):
        os.makedirs(pasta)
    return os.path.join(pasta, "pending_reports.json")


def instalar_em_local_fixo():
    """Copia o executável atual para uma pasta fixa e retorna o caminho de destino."""
    if not getattr(sys, "frozen", False):
        logger.info("Execução em modo script; auto-instalação não será feita.")
        return None

    origem = os.path.abspath(sys.executable)
    destino = caminho_instalacao()

    if os.path.normcase(origem) != os.path.normcase(destino):
        shutil.copy2(origem, destino)
        logger.info("Executável copiado para local fixo: %s", destino)
    else:
        logger.info("Executável já está no local fixo: %s", destino)

    return destino


def registrar_tarefa_agendada():
    """Cria a tarefa no Agendador para executar o agente no logon do usuário."""
    if not getattr(sys, "frozen", False):
        logger.info("Execução em modo script; tarefa agendada não será criada automaticamente.")
        return

    executavel = instalar_em_local_fixo()
    if not executavel:
        return

    comando = [
        "schtasks",
        "/Create",
        "/TN",
        NOME_TAREFA,
        "/SC",
        "ONLOGON",
        "/TR",
        f'"{executavel}"',
        "/RL",
        "LIMITED",
        "/F",
    ]

    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode == 0:
        logger.info(f"Tarefa agendada criada/atualizada: {NOME_TAREFA}")
        return

    if "já existe" in (resultado.stdout + resultado.stderr).lower():
        logger.info(f"Tarefa agendada já existe: {NOME_TAREFA}")
        return

    logger.error(
        "Falha ao criar tarefa agendada: %s",
        (resultado.stderr or resultado.stdout).strip()
    )


CREATE_NO_WINDOW = 0x08000000
TIMEOUT_COMANDO_SEGUNDOS = getattr(config, "TIMEOUT_COMANDO_SEGUNDOS", 300)

# Ponte de arquivos com a tarefa agendada elevada (roda como SYSTEM, registrada
# no onboarding) usada para comandos "modo admin": este processo roda sem
# privilégio e não consegue se autoelevar sem prompt de UAC, então delega a
# execução escrevendo o comando aqui e esperando a tarefa elevada (que fica
# monitorando essa pasta) devolver o resultado. A pasta é restrita via ACL só
# ao usuário deste notebook + SYSTEM.
_ADMIN_BRIDGE_DIR = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "InventarioTI", "admin-bridge")


def _admin_input_path(comando_id):
    # Um arquivo por comando (não um nome fixo compartilhado) -- assim, se um
    # comando travar do lado da tarefa elevada (ex: instalador esperando
    # reinício pendente), isso não impede outros comandos de serem entregues.
    return os.path.join(_ADMIN_BRIDGE_DIR, f"comando_{comando_id}.json")


def _admin_output_path(comando_id):
    return os.path.join(_ADMIN_BRIDGE_DIR, f"resultado_{comando_id}.json")
_ADMIN_POLL_SEGUNDOS = 2


def _subprocess_kwargs():
    kwargs = {"creationflags": CREATE_NO_WINDOW}
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    return kwargs


def _executar_comando(comando_texto):
    """Executa um comando remoto via PowerShell e retorna (sucesso, codigo_saida, saida_combinada)."""
    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-Command", comando_texto],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_COMANDO_SEGUNDOS,
            **_subprocess_kwargs(),
        )
        saida = (resultado.stdout or "") + (resultado.stderr or "")
        return resultado.returncode == 0, resultado.returncode, saida[:20000]
    except subprocess.TimeoutExpired:
        return False, None, f"Comando excedeu o tempo limite de {TIMEOUT_COMANDO_SEGUNDOS}s"
    except Exception as erro:
        return False, None, f"Erro ao executar comando: {erro}"


def _executar_comando_admin(comando_id, comando_texto):
    """Entrega o comando pra tarefa elevada (SYSTEM) via arquivo e espera o
    resultado. Se a tarefa elevada não estiver registrada nesta máquina (ex:
    onboarding antigo, sem a versão que criou a tarefa admin), simplesmente
    ninguém consome o arquivo e isso expira no timeout com um erro explicando."""
    input_path = _admin_input_path(comando_id)
    output_path = _admin_output_path(comando_id)

    try:
        os.makedirs(_ADMIN_BRIDGE_DIR, exist_ok=True)
    except Exception as erro:
        return False, None, f"Não foi possível preparar a pasta de comandos elevados: {erro}"

    try:
        if os.path.exists(output_path):
            os.remove(output_path)
    except Exception:
        pass

    try:
        with open(input_path, "w", encoding="utf-8") as arquivo:
            json.dump({"id": comando_id, "comando": comando_texto}, arquivo, ensure_ascii=False)
    except Exception as erro:
        return False, None, f"Não foi possível entregar o comando à tarefa elevada: {erro}"

    prazo = time.time() + TIMEOUT_COMANDO_SEGUNDOS
    while time.time() < prazo:
        time.sleep(_ADMIN_POLL_SEGUNDOS)
        if not os.path.exists(output_path):
            continue
        try:
            # utf-8-sig, não utf-8: o Windows PowerShell 5.1 (que roda a
            # tarefa elevada) grava esse arquivo com Set-Content -Encoding
            # UTF8, que inclui BOM. Com "utf-8" puro o BOM sobra colado no
            # início do texto e json.load falha em toda tentativa (silenciado
            # pelo except abaixo), fazendo o agente nunca ler um resultado que
            # já estava pronto -- só estourar no timeout de qualquer jeito.
            with open(output_path, "r", encoding="utf-8-sig") as arquivo:
                dados = json.load(arquivo)
        except Exception:
            continue
        try:
            os.remove(output_path)
        except Exception:
            pass
        codigo_saida = dados.get("codigo_saida")
        saida = str(dados.get("resultado") or "")[:20000]
        return codigo_saida == 0, codigo_saida, saida

    try:
        if os.path.exists(input_path):
            os.remove(input_path)
    except Exception:
        pass
    return False, None, (
        f"Tempo esgotado ({TIMEOUT_COMANDO_SEGUNDOS}s) esperando a tarefa elevada 'InventarioTI - Comando Admin'. "
        "Verifique se o onboarding foi executado (como administrador) nesta máquina depois que esse recurso "
        "foi adicionado, e se o Agendador de Tarefas do Windows está em execução."
    )


def _lidar_com_comando(cliente_ws, comando_id, comando_texto, modo):
    """Executa um comando recebido via push do WebSocket e reporta o
    resultado. Chamado numa thread própria por comando (agente_ws_client),
    pra um comando demorado não travar a conexão nem os demais comandos."""
    logger.info("Executando comando remoto #%s (modo=%s): %s", comando_id, modo, comando_texto)
    cliente_ws.enviar_ou_enfileirar({"type": "command_started", "id": comando_id})

    if modo == "admin":
        sucesso, codigo_saida, saida = _executar_comando_admin(comando_id, comando_texto)
    else:
        sucesso, codigo_saida, saida = _executar_comando(comando_texto)

    cliente_ws.enviar_ou_enfileirar(
        {
            "type": "command_result",
            "id": comando_id,
            "sucesso": sucesso,
            "codigo_saida": codigo_saida,
            "resultado": saida,
        }
    )
    logger.info("Comando #%s concluído (sucesso=%s)", comando_id, sucesso)



def coletar_dados_sistema():
    """Coleta OS, armazenamento e uso de CPU/memória/rede da máquina atual."""
    
    #--- Modelo e número de série do notebook ----
    modelo, numero_serie = obter_modelo_e_serial()

    # ---- Sistema Operacional ----
    sistema_operacional = f"{platform.system()} {platform.release()}"
    
    #---- Armazenamento (Disco Principal) ----
    disco = shutil.disk_usage("/") # No windows, funciona igual para o drive c:
    total_gb = round(disco.total / (1024 ** 3), 2)
    usado_gb = round(disco.used / (1024 ** 3), 2)
    livre_gb = round(disco.free / (1024 ** 3), 2)
    uso_disco_percentual = round((disco.used / disco.total) * 100, 1)
    
    # ---- CPU e memória ----
    uso_cpu_percentual = psutil.cpu_percent(interval=1)
    memoria = psutil.virtual_memory()
    uso_memoria_percentual = memoria.percent
    memoria_total_gb = round(memoria.total / (1024 ** 3), 2)
    memoria_usada_gb = round(memoria.used / (1024 ** 3), 2)

    #--- Rede ( Total acumulado desde que o sistema ligou ) ----
    rede = psutil.net_io_counters()
    rede_enviado_mb = round(rede.bytes_sent / (1024 ** 2), 2)
    rede_recebido_mb = round(rede.bytes_recv / (1024 ** 2), 2)


    return {
        "modelo": modelo,
        "numero_serie": numero_serie,
        "sistema_operacional": sistema_operacional,
        "disco_total_gb": total_gb,
        "disco_usado_gb": usado_gb,
        "disco_livre_gb": livre_gb,
        "uso_disco_percentual": uso_disco_percentual,
        "uso_cpu_percentual": uso_cpu_percentual,
        "uso_memoria_percentual": uso_memoria_percentual,
        "memoria_total_gb": memoria_total_gb,
        "memoria_usada_gb": memoria_usada_gb,
        "rede_enviado_mb": rede_enviado_mb,
        "rede_recebido_mb": rede_recebido_mb
    }
    
SERIAIS_INVALIDOS = {
    "",
    "to be filled by o.e.m.",
    "system serial number",
    "none",
    "default string",
    "0",
    "0000000000",
    "invalid",
}


def _identificador_unico_por_mac() -> str:
    """Usado quando o BIOS não expõe (ou expõe um placeholder de fábrica em vez
    de) um número de série de verdade — comum em algumas placas/BIOS antigos ou
    máquinas virtuais. Gera um identificador estável baseado no MAC address, pra
    cada equipamento sem serial real continuar tendo uma identidade própria em
    vez de todos colidirem no mesmo valor fixo "Desconhecido" (numero_serie é
    chave única na tabela de monitoramento, então essa colisão faz um segundo
    notebook nessa situação se misturar com o registro do primeiro)."""
    mac = uuid.getnode()
    return f"SEM-SERIAL-{mac:012X}"


def obter_modelo_e_serial():
    """Captura o modelo e número de série do notebook usando comandos do sistema."""
    modelo = "Desconhecido"
    serial = ""

    try:
        modelo = subprocess.check_output(
            ["powershell", "-Command", "(Get-CimInstance -ClassName Win32_ComputerSystem).Model"],
            text=True
        ).strip() or "Desconhecido"
    except Exception as e:
        logger.error(f"Erro ao obter modelo do equipamento: {e}")

    try:
        serial = subprocess.check_output(
            ["powershell", "-command", "(get-CimInstance win32_BIOS).SerialNumber"],
            text=True
        ).strip()
    except Exception as e:
        logger.error(f"Erro ao obter número de série do equipamento: {e}")

    if serial.strip().lower() in SERIAIS_INVALIDOS:
        serial_gerado = _identificador_unico_por_mac()
        logger.warning(
            "Número de série do BIOS indisponível/inválido (%r); usando identificador baseado no MAC: %s",
            serial,
            serial_gerado,
        )
        serial = serial_gerado

    return modelo, serial


def executar_loop():
    """Mantém uma conexão WebSocket persistente com o servidor (comandos chegam
    na hora, empurrados pelo servidor, em vez de esperar um ciclo de consulta)
    e, no thread principal, envia um relatório de monitoramento a cada
    INTERVALO_HORAS."""
    intervalo_relatorio_segundos = config.INTERVALO_HORAS * 60 * 60
    numero_serie_atual = None

    def numero_serie_fn():
        return numero_serie_atual

    def lidar_com_comando(comando_id, comando_texto, modo):
        _lidar_com_comando(cliente_ws, comando_id, comando_texto, modo)

    agente_identidade_http.iniciar_servidor_identidade(numero_serie_fn)

    cliente_ws = agente_ws_client.ClienteAgenteWS(
        ENDERECOS_SERVIDOR,
        getattr(config, "PORTA_BACKEND_WS", 8000),
        API_KEY,
        numero_serie_fn=numero_serie_fn,
        on_command=lidar_com_comando,
        caminho_fila=caminho_fila_local(),
        fila_max_itens=FILA_MAX_ITENS,
    )
    cliente_ws.iniciar()

    while True:
        dados = coletar_dados_sistema()
        dados["coletado_em"] = datetime.now().isoformat()
        numero_serie_atual = dados.get("numero_serie")
        cliente_ws.enviar_ou_enfileirar({"type": "monitoring", "data": dados})
        time.sleep(intervalo_relatorio_segundos)
        
    
    
if __name__ == "__main__":
    registrar_tarefa_agendada()
    executar_loop()