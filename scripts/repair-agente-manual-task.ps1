param(
    [string]$SourceExe = "",
    [string]$TaskName = "InventarioTI - Agente_manual"
)

$ErrorActionPreference = "Stop"

$baseDir = Join-Path $env:ProgramData "InventarioTI"
$installDir = $baseDir
$targetExe = Join-Path $installDir "Agente_manual.exe"

if ([string]::IsNullOrWhiteSpace($SourceExe)) {
    $candidates = @(
        (Join-Path $PSScriptRoot "Agente_manual.exe"),
        (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "Agente_manual.exe"),
        (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "dist\Agente_manual.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $SourceExe = $candidate
            break
        }
    }
}

New-Item -ItemType Directory -Path $installDir -Force | Out-Null

if (-not [string]::IsNullOrWhiteSpace($SourceExe) -and (Test-Path $SourceExe)) {
    Copy-Item -Path $SourceExe -Destination $targetExe -Force
    Write-Host "Executável copiado para: $targetExe" -ForegroundColor Green
} elseif (-not (Test-Path $targetExe)) {
    throw "Agente_manual.exe não encontrado para reparo. Informe -SourceExe com um caminho válido."
} else {
    Write-Host "Executável já existe em: $targetExe" -ForegroundColor Yellow
}

$action = New-ScheduledTaskAction -Execute $targetExe
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "Tarefa reparada: $TaskName" -ForegroundColor Green

Write-Host "Resumo da tarefa:" -ForegroundColor Cyan
schtasks /Query /TN $TaskName /V /FO LIST | findstr /I "Nome da tarefa Tarefa a ser executada Hora da próxima execução Horário da última execução Último resultado Executar como Usuário" | Out-Host

Write-Host "Disparando execução imediata para validação..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TaskName
Write-Host "Rode também: Get-Content C:\ProgramData\InventarioTI\logs\agente_manual.log -Tail 30" -ForegroundColor White
