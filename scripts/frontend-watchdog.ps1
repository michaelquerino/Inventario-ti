param(
    [string]$RepoRoot = "",
    [string]$NodeExe = "",
    # Vazio por padrão de propósito: sem override, o frontend deriva a URL da
    # API a partir do hostname que o navegador usou pra acessar a página
    # (localhost, IP da LAN ou VPN -- veja frontend/src/lib/session.ts). Só
    # defina isso se a API rodar num host/porta diferente do frontend.
    [string]$ApiBaseUrl = "",
    [int]$Port = 3000
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$frontendRoot = Join-Path $RepoRoot "frontend"
if (-not (Test-Path $frontendRoot)) {
    throw "Pasta frontend nao encontrada: $frontendRoot"
}

if ([string]::IsNullOrWhiteSpace($NodeExe)) {
    $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCmd) {
        throw "Node.js nao encontrado no PATH."
    }
    $NodeExe = $nodeCmd.Source
}

$nextBin = Join-Path $frontendRoot "node_modules\next\dist\bin\next"
if (-not (Test-Path $nextBin)) {
    throw "Next.js nao encontrado em $nextBin. Instale as dependencias do frontend antes de iniciar o watchdog."
}

$logsDir = Join-Path $RepoRoot "logs"
if (-not (Test-Path $logsDir)) {
    New-Item -Path $logsDir -ItemType Directory | Out-Null
}

$frontendLog = Join-Path $logsDir "frontend-service.log"
$frontendErrLog = Join-Path $logsDir "frontend-service.err.log"
$watchdogLog = Join-Path $logsDir "frontend-watchdog.log"

function Write-WatchdogLog([string]$Message) {
    $line = "$(Get-Date -Format s) - $Message"
    Add-Content -Path $watchdogLog -Value $line
}

function Test-FrontendOnline {
    try {
        $client = New-Object Net.Sockets.TcpClient
        $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(2000, $false)
        if (-not $ok) {
            $client.Close()
            return $false
        }
        $client.EndConnect($iar)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

function Start-Frontend {
    Write-WatchdogLog "Frontend offline. Iniciando processo na porta $Port."
    if ([string]::IsNullOrWhiteSpace($ApiBaseUrl)) {
        Remove-Item Env:\NEXT_PUBLIC_API_URL -ErrorAction SilentlyContinue
    } else {
        $env:NEXT_PUBLIC_API_URL = $ApiBaseUrl
    }
    try {
        Start-Process -FilePath $NodeExe -ArgumentList @($nextBin, "dev", "-H", "0.0.0.0", "-p", $Port) -WorkingDirectory $frontendRoot -WindowStyle Hidden -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErrLog | Out-Null
    } catch {
        Write-WatchdogLog "Falha ao iniciar frontend: $($_.Exception.Message)"
    }
}

Write-WatchdogLog "Watchdog do frontend iniciado. RepoRoot=$RepoRoot NodeExe=$NodeExe ApiBaseUrl=$ApiBaseUrl Port=$Port"

while ($true) {
    try {
        if (-not (Test-FrontendOnline)) {
            Start-Frontend
        }
    } catch {
        # Nunca deixa um erro de uma iteração matar o loop inteiro do watchdog
        # -- sem isso, um erro passageiro (ex: log em uso por um instante)
        # derruba o supervisor e o frontend fica pra sempre sem ninguém
        # reiniciando ele.
        Write-WatchdogLog "Erro no loop do watchdog (ignorado, tenta de novo no próximo ciclo): $($_.Exception.Message)"
    }

    Start-Sleep -Seconds 60
}
