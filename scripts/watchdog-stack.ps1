param(
    [string]$RepoRoot = "",
    [string]$PythonExe = "python",
    [string]$PythonArgs = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$logsDir = Join-Path $RepoRoot "logs"
if (-not (Test-Path $logsDir)) {
    New-Item -Path $logsDir -ItemType Directory | Out-Null
}

$backendLog = Join-Path $logsDir "backend-service.log"
$backendErrLog = Join-Path $logsDir "backend-service.err.log"
$collectorLog = Join-Path $logsDir "collector-service.log"
$collectorErrLog = Join-Path $logsDir "collector-service.err.log"
$watchdogLog = Join-Path $logsDir "watchdog.log"

function Write-WatchdogLog([string]$Message) {
    $line = "$(Get-Date -Format s) - $Message"
    Add-Content -Path $watchdogLog -Value $line
}

function Test-BackendOnline {
    try {
        $tcp = New-Object Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect("127.0.0.1", 8000, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(2000, $false)
        if (-not $ok) {
            $tcp.Close()
            return $false
        }
        $tcp.EndConnect($iar)
        $tcp.Close()
        return $true
    } catch {
        return $false
    }
}

function Test-CollectorOnline {
    try {
        $tcp = New-Object Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect("127.0.0.1", 5000, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(2000, $false)
        if (-not $ok) {
            $tcp.Close()
            return $false
        }
        $tcp.EndConnect($iar)
        $tcp.Close()
        return $true
    } catch {
        return $false
    }
}

function Start-Backend {
    Write-WatchdogLog "Backend offline. Iniciando processo."
    $args = @()
    if (-not [string]::IsNullOrWhiteSpace($PythonArgs)) {
        $args += $PythonArgs
    }
    $args += @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend")
    try {
        Start-Process -FilePath $PythonExe -ArgumentList $args -WorkingDirectory $RepoRoot -WindowStyle Hidden -RedirectStandardOutput $backendLog -RedirectStandardError $backendErrLog | Out-Null
    } catch {
        Write-WatchdogLog "Falha ao iniciar backend: $($_.Exception.Message)"
    }
}

# DEPRECADO (servidor.py/Flask, porta 5000): nenhum build atual do agente
# (agente.py nem agente_manual.py) chama mais os endpoints HTTP antigos
# (/reportar, /comandos) -- os dois falam só com o backend FastAPI via
# WebSocket agora. O único endpoint que ainda era usado (/agente/download,
# pro botão "Atualizar agente") foi migrado pro próprio backend (veja
# backend/app/api/routes/agent_ws.py). Start-Collector não é mais chamado no
# loop principal abaixo -- mantido aqui só de referência, caso precise
# reativar temporariamente por algum motivo.
function Start-Collector {
    Write-WatchdogLog "Coletor offline. Iniciando processo."
    $args = @()
    if (-not [string]::IsNullOrWhiteSpace($PythonArgs)) {
        $args += $PythonArgs
    }
    $args += "servidor.py"
    try {
        Start-Process -FilePath $PythonExe -ArgumentList $args -WorkingDirectory $RepoRoot -WindowStyle Hidden -RedirectStandardOutput $collectorLog -RedirectStandardError $collectorErrLog | Out-Null
    } catch {
        Write-WatchdogLog "Falha ao iniciar coletor: $($_.Exception.Message)"
    }
}

Write-WatchdogLog "Watchdog iniciado. RepoRoot=$RepoRoot PythonExe=$PythonExe PythonArgs=$PythonArgs"

while ($true) {
    try {
        if (-not (Test-BackendOnline)) {
            Start-Backend
        }

        # Coletor Flask (servidor.py) aposentado -- ver comentário acima de
        # Start-Collector. Se a porta 5000 ainda estiver com um processo
        # antigo escutando (de antes desta mudança), ele simplesmente
        # continua rodando até alguém parar manualmente; o watchdog só não
        # sobe um novo se cair.
    } catch {
        # Nunca deixa um erro de uma iteração matar o loop inteiro do watchdog.
        Write-WatchdogLog "Erro no loop do watchdog (ignorado, tenta de novo no próximo ciclo): $($_.Exception.Message)"
    }

    Start-Sleep -Seconds 60
}
