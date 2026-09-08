param(
    [string]$BackendTaskName = "Inventario-Stack-Watchdog",
    [string]$FrontendTaskName = "Inventario-Frontend-Watchdog",
    # Vazio por padrão: sem override, o frontend deriva a URL da API a partir
    # do hostname usado pra acessar a página (veja frontend-watchdog.ps1).
    [string]$FrontendApiBaseUrl = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$watchdogScript = Join-Path $repoRoot "scripts\watchdog-stack.ps1"
$frontendWatchdogScript = Join-Path $repoRoot "scripts\frontend-watchdog.ps1"

if (-not (Test-Path $watchdogScript)) {
    throw "Script nao encontrado: $watchdogScript"
}

if (-not (Test-Path $frontendWatchdogScript)) {
    throw "Script nao encontrado: $frontendWatchdogScript"
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if (-not $pyCmd) {
        throw "Python nao encontrado no PATH para criar o servico."
    }
    $pythonExe = $pyCmd.Source
    $pythonArgs = "-3"
} else {
    $pythonExe = $pythonCmd.Source
    $pythonArgs = ""
}

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    # Preferred: Scheduled Task running as SYSTEM, starts at boot (no logon required)
    $escapedRepo   = $repoRoot.Replace('"', '""')
    $escapedPyExe  = $pythonExe.Replace('"', '""')
    $escapedPyArgs = $pythonArgs.Replace('"', '""')
    $escapedScript = $watchdogScript.Replace('"', '""')
    $escapedFrontendScript = $frontendWatchdogScript.Replace('"', '""')
    $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCmd) {
        throw "Node.js nao encontrado no PATH para o autostart do frontend."
    }
    $nodeExe = $nodeCmd.Source.Replace('"', '""')
    $escapedFrontendApi = $FrontendApiBaseUrl.Replace('"', '""')

    $psArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$escapedScript`" -RepoRoot `"$escapedRepo`" -PythonExe `"$escapedPyExe`""
    if ($escapedPyArgs) { $psArgs += " -PythonArgs `"$escapedPyArgs`"" }

    $action    = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs
    $trigger   = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest -LogonType ServiceAccount
    $settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

    Register-ScheduledTask -TaskName $BackendTaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $BackendTaskName

    $frontendArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$escapedFrontendScript`" -RepoRoot `"$escapedRepo`" -NodeExe `"$nodeExe`" -ApiBaseUrl `"$escapedFrontendApi`""
    $frontendAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $frontendArgs
    Register-ScheduledTask -TaskName $FrontendTaskName -Action $frontendAction -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $FrontendTaskName

    Write-Host "Tarefas agendadas instaladas com sucesso:" -ForegroundColor Green
    Write-Host "- $BackendTaskName"
    Write-Host "- $FrontendTaskName"
    Write-Host "Modo: SYSTEM / AtStartup (inicio automatico sem logon)"
    Write-Host "Para remover: Unregister-ScheduledTask -TaskName '<nome>' -Confirm:`$false"
} else {
    # Fallback: launcher .bat + Registry Run key (no elevation needed, starts at user logon)
    $launcherPath = Join-Path $repoRoot "scripts\start-watchdog.bat"
    $frontendLauncherPath = Join-Path $repoRoot "scripts\start-frontend.bat"
    $frontendNodeCmd = Get-Command node -ErrorAction SilentlyContinue
    if (-not $frontendNodeCmd) {
        throw "Node.js nao encontrado no PATH para o autostart do frontend."
    }
    $frontendNodeExe = $frontendNodeCmd.Source

    $psLine = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$watchdogScript`" -RepoRoot `"$repoRoot`" -PythonExe `"$pythonExe`""
    if ($pythonArgs) { $psLine += " -PythonArgs `"$pythonArgs`"" }

    $batContent = "@echo off`r`n$psLine`r`n"
    [System.IO.File]::WriteAllText($launcherPath, $batContent, [System.Text.Encoding]::ASCII)

    $frontendPsLine = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$frontendWatchdogScript`" -RepoRoot `"$repoRoot`" -NodeExe `"$frontendNodeExe`" -ApiBaseUrl `"$FrontendApiBaseUrl`""
    $frontendBatContent = "@echo off`r`n$frontendPsLine`r`n"
    [System.IO.File]::WriteAllText($frontendLauncherPath, $frontendBatContent, [System.Text.Encoding]::ASCII)

    $regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    Set-ItemProperty -Path $regPath -Name $BackendTaskName -Value "`"$launcherPath`"" -Type String
    Set-ItemProperty -Path $regPath -Name $FrontendTaskName -Value "`"$frontendLauncherPath`"" -Type String

    Write-Host "Autostart instalado via registro do usuario:" -ForegroundColor Yellow
    Write-Host "- $BackendTaskName"
    Write-Host "- $FrontendTaskName"
    Write-Host "Modo: HKCU Run key / logon (requer que o usuario Admin faca login)"
    Write-Host "Launcher: $launcherPath"
    Write-Host "Launcher frontend: $frontendLauncherPath"
    Write-Host ""
    Write-Host "AVISO: Para inicio automatico sem logon (recomendado), execute este" -ForegroundColor Cyan
    Write-Host "       script novamente em um PowerShell como Administrador." -ForegroundColor Cyan
    Write-Host "Para remover o registro: Remove-ItemProperty -Path '$regPath' -Name '<nome>'"
}

Write-Host ""
Write-Host "Repositorio: $repoRoot"
Write-Host "Python: $pythonExe $pythonArgs"
