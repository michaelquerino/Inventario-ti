# Só é necessário rodar isso em notebooks que NÃO conseguem alcançar o
# servidor pela rede local (192.168.1.x ou 192.168.8.x) -- ex: notebooks em
# outra sub-rede/filial. Se o notebook já está online normalmente depois do
# onboarding, pode pular este script.
#
# Precisa ser rodado localmente (com acesso físico/RDP à máquina), como
# Administrador: sem conectividade nenhuma com o servidor, não tem como
# entregar isso por comando remoto.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$outroInstalador = Get-Process msiexec -ErrorAction SilentlyContinue
if ($outroInstalador) {
    Write-Host "Aviso: ja existe um processo msiexec rodando (pode ser Windows Update). Se a instalacao falhar com 'outro programa esta sendo instalado', aguarde alguns minutos e rode este script de novo." -ForegroundColor Yellow
}

$msi = Join-Path $env:TEMP 'tailscale-setup.msi'
Write-Host "Baixando instalador do Tailscale..." -ForegroundColor Cyan
Invoke-WebRequest -Uri "https://pkgs.tailscale.com/stable/tailscale-setup-1.102.2-amd64.msi" -OutFile $msi -UseBasicParsing

Write-Host "Instalando (silencioso)..." -ForegroundColor Cyan
$proc = Start-Process msiexec.exe -ArgumentList @('/i', $msi, '/quiet', '/norestart') -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    throw "msiexec falhou com codigo $($proc.ExitCode). Verifique se ha outra instalacao em andamento e tente novamente."
}

Start-Sleep -Seconds 10

$tailscaleExe = "C:\Program Files\Tailscale\tailscale.exe"
if (-not (Test-Path $tailscaleExe)) {
    throw "Instalacao concluida mas $tailscaleExe nao foi encontrado. Reinicie o notebook e rode este script de novo."
}

# O instalador abre a interface grafica (tailscale-ipn.exe) sozinha logo apos
# a instalacao, que entra num fluxo de login interativo proprio e atrapalha o
# "tailscale up --auth-key" rodando em seguida via linha de comando. Fecha
# essa janela antes de autenticar pra nao ter os dois brigando.
Get-Process -Name "tailscale-ipn" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "Conectando na rede Tailscale..." -ForegroundColor Cyan
& $tailscaleExe up --auth-key=tskey-auth-kJXNzgWvQ621CNTRL-Zrdnkjh7AX84LtMF8JcBX8rEyYqfCC9ZS --unattended
& $tailscaleExe status

Write-Host "`nPronto. Confira se recebeu um IP 100.x.x.x acima." -ForegroundColor Green
