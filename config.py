"""
Configurações do agente de monitoramento.
Altere apenas o IP_SERVIDOR conforme o ambiente:
- "localhost"        -> testes na mesma máquina
- "192.168.x.x"      -> rede local (mesma rede Wi-Fi/cabo do servidor)
- IP da VPN          -> quando o notebook está fora da rede local (ex: Tailscale)
"""

import os

IP_SERVIDOR_LOCAL = os.getenv("IP_SERVIDOR_LOCAL", "")
IP_SERVIDOR_PRINCIPAL = os.getenv("IP_SERVIDOR_PRINCIPAL", "192.168.1.87")
IP_SERVIDOR_VPN = os.getenv("IP_SERVIDOR_VPN", "192.168.8.35")
# IP do servidor dentro da rede Tailscale -- alcançável de qualquer lugar
# (LAN ou fora dela) desde que o notebook também tenha o Tailscale instalado,
# sem precisar abrir VPN manualmente. Funciona como mais um endereço que o
# agente tenta; notebooks sem Tailscale instalado simplesmente não conseguem
# alcançar esse IP e caem para LAN/VPN normalmente, como já fazia antes.
IP_SERVIDOR_TAILSCALE = os.getenv("IP_SERVIDOR_TAILSCALE", "100.95.222.38")
# Nome de rede resolvido pelo arquivo hosts de cada notebook (mesmo mecanismo
# já usado pela tela de chamados, veja onboarding-notebook.ps1). Tentar esse
# nome além do IP fixo evita que uma futura troca de servidor (ex: migração
# pra outra máquina/IP) exija recompilar e reenviar o agente pra frota
# inteira -- basta atualizar o hosts file remotamente, que já é scriptável.
IP_SERVIDOR_NOME = os.getenv("IP_SERVIDOR_NOME", "infradesk")
PORTA_SERVIDOR = int(os.getenv("PORTA_SERVIDOR", "5000"))
# Porta do backend FastAPI que hospeda o endpoint /ws/agent (substitui o
# polling HTTP antigo, que continua em PORTA_SERVIDOR pros agentes que ainda
# não foram atualizados).
PORTA_BACKEND_WS = int(os.getenv("PORTA_BACKEND_WS", "8000"))
INTERVALO_HORAS = 0.5

# Comandos remotos: intervalo de checagem (mais curto que o relatório completo,
# pra resposta ser rápida) e tempo máximo de execução de um comando.
COMANDOS_INTERVALO_SEGUNDOS = 60
TIMEOUT_COMANDO_SEGUNDOS = 300

ENDERECOS_SERVIDOR = [
    ip
    for ip in [IP_SERVIDOR_PRINCIPAL, IP_SERVIDOR_NOME, IP_SERVIDOR_TAILSCALE, IP_SERVIDOR_VPN, IP_SERVIDOR_LOCAL]
    if ip and str(ip).strip()
]

# Chave de API para autenticação servidor-agente (mesma em ambos). Pode ser
# sobrescrita por variável de ambiente (mesmo padrão usado pelos IPs acima),
# pra permitir rotacionar sem editar/recompilar este arquivo em todo lugar --
# o valor abaixo é só o padrão de fábrica, igual ao já usado até aqui.
API_KEY_SERVIDOR = os.getenv("API_KEY_SERVIDOR", "fmH5kwsA-HcfqcaKqbqRAPiBQNHn03296nGNPwUHA_k")
API_KEY_AGENTE = os.getenv("API_KEY_AGENTE", "fmH5kwsA-HcfqcaKqbqRAPiBQNHn03296nGNPwUHA_k")

# Caminho do executável do agente que o servidor disponibiliza para
# autoatualização remota via comando (veja rota /agente/download em
# servidor.py). Após gerar um novo build com o PyInstaller, basta o
# arquivo em dist/agente_manual.exe ser substituído para a nova versão
# passar a ser distribuída.
AGENTE_EXE_PATH = os.getenv(
    "AGENTE_EXE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "agente_manual.exe"),
)
