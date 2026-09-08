"""
Agente manual de monitoramento — igual ao agente padrão, mas com cadastro inicial
obrigatório de vínculo (usuário e patrimônios) para sincronização automática.
"""

import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime

import psutil
import config

import agente_identidade_http
import agente_ws_client

try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog
except Exception:
    tk = None
    messagebox = None
    simpledialog = None

# Evita nomes com acento corrompidos (ex: "Marihá" -> "MarihÃ¡") quando o
# fallback de console (_solicitar_via_console) é usado num console com
# codepage OEM legado em vez de UTF-8.
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


def caminho_log():
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    pasta = os.path.join(base, "InventarioTI", "logs")
    if not os.path.exists(pasta):
        os.makedirs(pasta)
    return os.path.join(pasta, "agente_manual.log")


def caminho_instalacao():
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    pasta = os.path.join(base, "InventarioTI")
    if not os.path.exists(pasta):
        os.makedirs(pasta)
    return os.path.join(pasta, "Agente_manual.exe")


def caminho_vinculo_local():
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    pasta = os.path.join(base, "InventarioTI", "config")
    if not os.path.exists(pasta):
        os.makedirs(pasta)
    return os.path.join(pasta, "agente_manual_vinculo.json")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(caminho_log(), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Evita que cada chamada de subprocess (powershell, schtasks) abra uma
# janela de console visivel -- sem isso, mesmo com o exe compilado sem
# console proprio (--noconsole), todo subprocesso cria a sua propria janela.
CREATE_NO_WINDOW = 0x08000000


def _subprocess_kwargs():
    kwargs = {"creationflags": CREATE_NO_WINDOW}
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    return kwargs


ENDERECOS_SERVIDOR = getattr(
    config,
    "ENDERECOS_SERVIDOR",
    [config.IP_SERVIDOR_PRINCIPAL, config.IP_SERVIDOR_VPN],
)
API_KEY = getattr(config, "API_KEY_AGENTE", "chave-padrao-alterar")
NOME_TAREFA = "InventarioTI - Agente_manual"
FILA_MAX_ITENS = getattr(config, "FILA_MAX_ITENS", 500)


def caminho_fila_local():
    """Arquivo onde mensagens (relatórios de monitoramento, início/resultado
    de comando) ficam guardadas quando não há conexão WebSocket ativa no
    momento do envio, até serem reenviadas na próxima reconexão."""
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    pasta = os.path.join(base, "InventarioTI", "queue")
    if not os.path.exists(pasta):
        os.makedirs(pasta)
    return os.path.join(pasta, "pending_reports_manual.json")


def instalar_em_local_fixo():
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


def registrar_tarefa_agendada(nome_tarefa=None):
    nome_tarefa = nome_tarefa or NOME_TAREFA

    if not getattr(sys, "frozen", False):
        logger.info("Execução em modo script; tarefa agendada não será criada automaticamente.")
        return

    executavel = instalar_em_local_fixo()
    if not executavel:
        return

    consulta = subprocess.run(
        ["schtasks", "/Query", "/TN", nome_tarefa],
        capture_output=True,
        text=True,
        **_subprocess_kwargs(),
    )
    if consulta.returncode == 0:
        logger.info("Tarefa agendada já existe: %s", nome_tarefa)
        return

    comando = [
        "schtasks",
        "/Create",
        "/TN",
        nome_tarefa,
        "/SC",
        "ONLOGON",
        "/TR",
        f'"{executavel}"',
        "/RL",
        "LIMITED",
        "/F",
    ]

    resultado = subprocess.run(comando, capture_output=True, text=True, **_subprocess_kwargs())
    if resultado.returncode == 0:
        logger.info("Tarefa agendada criada/atualizada: %s", nome_tarefa)
        return

    if "já existe" in (resultado.stdout + resultado.stderr).lower():
        logger.info("Tarefa agendada já existe: %s", nome_tarefa)
        return

    logger.error("Falha ao criar tarefa agendada: %s", (resultado.stderr or resultado.stdout).strip())


TIMEOUT_COMANDO_SEGUNDOS = getattr(config, "TIMEOUT_COMANDO_SEGUNDOS", 300)

# Ponte de arquivos com a tarefa agendada elevada (roda como SYSTEM, registrada
# no onboarding) usada para comandos "modo admin": este processo roda sem
# privilégio (de propósito, veja onboarding-notebook.ps1) e não consegue se
# autoelevar sem prompt de UAC, então delega a execução escrevendo o comando
# aqui e esperando a tarefa elevada (que fica monitorando essa pasta) devolver
# o resultado. A pasta é restrita via ACL só ao usuário deste notebook + SYSTEM.
_ADMIN_BRIDGE_DIR = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "InventarioTI", "admin-bridge")
_ADMIN_POLL_SEGUNDOS = 2


def _admin_input_path(comando_id):
    # Um arquivo por comando (não um nome fixo compartilhado) -- assim, se um
    # comando travar do lado da tarefa elevada (ex: instalador esperando
    # reinício pendente), isso não impede outros comandos de serem entregues.
    return os.path.join(_ADMIN_BRIDGE_DIR, f"comando_{comando_id}.json")


def _admin_output_path(comando_id):
    return os.path.join(_ADMIN_BRIDGE_DIR, f"resultado_{comando_id}.json")


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
    modelo = "Desconhecido"
    serial = ""

    try:
        modelo = subprocess.check_output(
            ["powershell", "-Command", "(Get-CimInstance -ClassName Win32_ComputerSystem).Model"],
            text=True,
            **_subprocess_kwargs(),
        ).strip() or "Desconhecido"
    except Exception as erro:
        logger.error("Erro ao obter modelo do equipamento: %s", erro)

    try:
        serial = subprocess.check_output(
            ["powershell", "-Command", "(Get-CimInstance Win32_BIOS).SerialNumber"],
            text=True,
            **_subprocess_kwargs(),
        ).strip()
    except Exception as erro:
        logger.error("Erro ao obter número de série do equipamento: %s", erro)

    if serial.strip().lower() in SERIAIS_INVALIDOS:
        serial_gerado = _identificador_unico_por_mac()
        logger.warning(
            "Número de série do BIOS indisponível/inválido (%r); usando identificador baseado no MAC: %s",
            serial,
            serial_gerado,
        )
        serial = serial_gerado

    return modelo, serial


def coletar_dados_sistema():
    modelo, numero_serie = obter_modelo_e_serial()
    sistema_operacional = f"{platform.system()} {platform.release()}"

    disco = shutil.disk_usage("/")
    total_gb = round(disco.total / (1024 ** 3), 2)
    usado_gb = round(disco.used / (1024 ** 3), 2)
    livre_gb = round(disco.free / (1024 ** 3), 2)
    uso_disco_percentual = round((disco.used / disco.total) * 100, 1)

    uso_cpu_percentual = psutil.cpu_percent(interval=1)
    memoria = psutil.virtual_memory()
    uso_memoria_percentual = memoria.percent
    memoria_total_gb = round(memoria.total / (1024 ** 3), 2)
    memoria_usada_gb = round(memoria.used / (1024 ** 3), 2)

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
        "rede_recebido_mb": rede_recebido_mb,
    }


def _solicitar_via_console(dados_atuais=None):
    dados_atuais = dados_atuais or {}

    print("\nCadastro inicial do Agente_manual")
    print("Preencha os dados para vínculo automático no inventário.\n")

    usuario = ""
    while not usuario:
        sufixo = f" [{dados_atuais.get('usuario', '').strip()}]" if dados_atuais.get("usuario") else ""
        resposta = input(f"Usuário{sufixo}: ").strip()
        usuario = resposta or (dados_atuais.get("usuario", "").strip())

    patrimonio = ""
    while not patrimonio:
        sufixo = f" [{dados_atuais.get('patrimonio', '').strip()}]" if dados_atuais.get("patrimonio") else ""
        resposta = input(f"Patrimônio Notebook{sufixo}: ").strip()
        patrimonio = resposta or (dados_atuais.get("patrimonio", "").strip())

    atual_monitor = (dados_atuais.get("patrimonio_monitor") or "").strip()
    sufixo_monitor = f" [{atual_monitor}]" if atual_monitor else ""
    patrimonio_monitor = input(f"Patrimônio tela (caso tenha){sufixo_monitor}: ").strip() or atual_monitor

    return {
        "usuario": usuario,
        "patrimonio": patrimonio,
        "patrimonio_monitor": patrimonio_monitor,
    }


def _solicitar_via_janela(dados_atuais=None):
    dados_atuais = dados_atuais or {}

    if tk is None or simpledialog is None:
        return _solicitar_via_console(dados_atuais)

    dialog = simpledialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    if messagebox is not None:
        messagebox.showinfo(
            "Agente_manual",
            "Preencha as informações para vínculo automático no sistema.",
            parent=root,
        )

    def pedir_obrigatorio(titulo, texto, valor_inicial=""):
        valor = ""
        while not valor:
            resposta = dialog.askstring(titulo, texto, parent=root, initialvalue=valor_inicial)
            if resposta is None:
                continue
            valor = resposta.strip()
        return valor

    usuario = pedir_obrigatorio("Agente_manual", "Usuário:", (dados_atuais.get("usuario") or "").strip())
    patrimonio = pedir_obrigatorio(
        "Agente_manual",
        "Patrimônio Notebook:",
        (dados_atuais.get("patrimonio") or "").strip(),
    )
    patrimonio_monitor = dialog.askstring(
        "Agente_manual",
        "Patrimônio tela (caso tenha):",
        parent=root,
        initialvalue=(dados_atuais.get("patrimonio_monitor") or "").strip(),
    )

    root.destroy()

    return {
        "usuario": usuario,
        "patrimonio": patrimonio,
        "patrimonio_monitor": (patrimonio_monitor or "").strip(),
    }


def carregar_vinculo_manual():
    caminho = caminho_vinculo_local()
    if not os.path.exists(caminho):
        return None

    try:
        dados = None
        for encoding in ("utf-8", "utf-8-sig"):
            try:
                with open(caminho, "r", encoding=encoding) as arquivo:
                    dados = json.load(arquivo)
                break
            except json.JSONDecodeError:
                continue

        if dados is None:
            return None
        if not isinstance(dados, dict):
            return None
        usuario = (dados.get("usuario") or "").strip()
        patrimonio = (dados.get("patrimonio") or "").strip()
        if not usuario or not patrimonio:
            return None
        return {
            "usuario": usuario,
            "patrimonio": patrimonio,
            "patrimonio_monitor": (dados.get("patrimonio_monitor") or "").strip(),
        }
    except (OSError, json.JSONDecodeError):
        return None


def salvar_vinculo_manual(dados):
    caminho = caminho_vinculo_local()
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)


def obter_vinculo_manual(forcar=False):
    existente = carregar_vinculo_manual() or {}
    usuario = (existente.get("usuario") or "").strip()
    patrimonio = (existente.get("patrimonio") or "").strip()

    if not forcar and usuario and patrimonio:
        logger.info("Usando vínculo já salvo e pulando nova solicitação de cadastro.")
        return {
            "usuario": usuario,
            "patrimonio": patrimonio,
            "patrimonio_monitor": (existente.get("patrimonio_monitor") or "").strip(),
        }

    try:
        dados = _solicitar_via_janela(existente)
    except Exception as erro:
        logger.warning("Falha na solicitação via janela: %s. Usando console.", erro)
        dados = _solicitar_via_console(existente)

    salvar_vinculo_manual(dados)
    logger.info("Cadastro manual atualizado com sucesso.")
    return dados


def executar_loop():
    """Mantém uma conexão WebSocket persistente com o servidor (comandos chegam
    na hora, empurrados pelo servidor, em vez de esperar um ciclo de consulta)
    e, no thread principal, envia um relatório de monitoramento a cada
    INTERVALO_HORAS."""
    forcar = "--forcar" in sys.argv
    vinculo = obter_vinculo_manual(forcar=forcar)

    intervalo_relatorio_segundos = config.INTERVALO_HORAS * 60 * 60
    numero_serie_atual = None

    def numero_serie_fn():
        return numero_serie_atual

    def lidar_com_comando(comando_id, comando_texto, modo):
        _lidar_com_comando(cliente_ws, comando_id, comando_texto, modo)

    agente_identidade_http.iniciar_servidor_identidade(numero_serie_fn, vinculo_fn=lambda: vinculo)

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
        dados["usuario"] = vinculo.get("usuario", "")
        dados["patrimonio"] = vinculo.get("patrimonio", "")
        dados["patrimonio_monitor"] = vinculo.get("patrimonio_monitor", "")
        dados["coletado_em"] = datetime.now().isoformat()
        numero_serie_atual = dados.get("numero_serie")
        cliente_ws.enviar_ou_enfileirar({"type": "monitoring", "data": dados})
        time.sleep(intervalo_relatorio_segundos)


if __name__ == "__main__":
    registrar_tarefa_agendada()
    executar_loop()
