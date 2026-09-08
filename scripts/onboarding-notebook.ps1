param(
    [string]$Usuario = "",
    [string]$PatrimonioNotebook = "",
    [string]$PatrimonioTela = "",
    [string]$CaminhoAgente = "",
    [switch]$ConfigurarAutoStart = $true,
    [switch]$ForcarCadastro = $false
)

$ErrorActionPreference = "Stop"

# Sem isso, nomes com acento digitados no console (Read-Host) podem ser
# capturados com o codepage OEM legado do Windows e gravados corrompidos
# (ex: "Marihá" vira "MarihÃ¡") ao chegar no banco em UTF-8.
try {
    chcp 65001 | Out-Null
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
    Write-Host "Aviso: nao foi possivel forcar codepage UTF-8 do console ($($_.Exception.Message))" -ForegroundColor Yellow
}

if ([string]::IsNullOrWhiteSpace($CaminhoAgente)) {
    $CaminhoAgente = Join-Path $PSScriptRoot "Agente_manual.exe"
}

$base = Join-Path $env:ProgramData "InventarioTI"
$configDir = Join-Path $base "config"
$vinculoPath = Join-Path $configDir "agente_manual_vinculo.json"

if (([string]::IsNullOrWhiteSpace($Usuario) -or [string]::IsNullOrWhiteSpace($PatrimonioNotebook)) -and (Test-Path $vinculoPath)) {
    try {
        $vinculoExistente = Get-Content -Path $vinculoPath -Raw | ConvertFrom-Json
        if ([string]::IsNullOrWhiteSpace($Usuario) -and $vinculoExistente.usuario) {
            $Usuario = [string]$vinculoExistente.usuario
        }
        if ([string]::IsNullOrWhiteSpace($PatrimonioNotebook) -and $vinculoExistente.patrimonio) {
            $PatrimonioNotebook = [string]$vinculoExistente.patrimonio
        }
        if ([string]::IsNullOrWhiteSpace($PatrimonioTela) -and $null -ne $vinculoExistente.patrimonio_monitor) {
            $PatrimonioTela = [string]$vinculoExistente.patrimonio_monitor
        }
    } catch {
        Write-Host "Aviso: vínculo salvo inválido, será solicitado novamente." -ForegroundColor Yellow
    }
}

if ([string]::IsNullOrWhiteSpace($Usuario)) {
    $Usuario = Read-Host "Usuario do notebook"
}

if ([string]::IsNullOrWhiteSpace($PatrimonioNotebook)) {
    $PatrimonioNotebook = Read-Host "Patrimonio do notebook"
}

if ([string]::IsNullOrWhiteSpace($PatrimonioTela)) {
    $PatrimonioTela = Read-Host "Patrimonio da tela (opcional, Enter para vazio)"
}

if ([string]::IsNullOrWhiteSpace($Usuario)) {
    throw "Usuario nao informado."
}

if ([string]::IsNullOrWhiteSpace($PatrimonioNotebook)) {
    throw "Patrimonio do notebook nao informado."
}

if (-not (Test-Path $CaminhoAgente)) {
    throw "Agente_manual.exe nao encontrado em $CaminhoAgente"
}

$installDir = $base
$logDir = Join-Path $base "logs"

New-Item -Path $installDir -ItemType Directory -Force | Out-Null
New-Item -Path $configDir -ItemType Directory -Force | Out-Null
New-Item -Path $logDir -ItemType Directory -Force | Out-Null

# Estas pastas sao criadas pela conta elevada (admin), o que por padrao
# nega escrita ao usuario padrao do notebook. O agente roda no logon com
# o token do usuario comum e precisa gravar config/log ali, entao
# liberamos Modify para Usuarios Autenticados (SID universal, independe
# do idioma do Windows).
try {
    icacls $base /grant "*S-1-5-11:(OI)(CI)M" /T /C /Q | Out-Null
} catch {
    Write-Host "Aviso: nao foi possivel ajustar permissoes de $base ($($_.Exception.Message))" -ForegroundColor Yellow
}

# Nome amigavel "infradesk" no lugar do IP (http://infradesk:3000), via hosts
# file local -- nao precisa de servidor DNS proprio. Puramente aditivo: so
# garante que a linha exista, nunca remove nada que ja esteja no arquivo.
# Se a LAN principal (192.168.1.87) nao estiver alcancavel mas o Tailscale ja
# estiver instalado e conectado nesta maquina, aponta pro IP do Tailscale em
# vez disso -- do contrario mantem o padrao da LAN.
# Escrever em C:\Windows\System32\drivers\etc\hosts exige privilegio de
# administrador -- se este script nao estiver rodando elevado, o bloco abaixo
# falha e o nome nunca fica disponivel nesse notebook (avisa bem visivel pra
# nao passar despercebido, ja aconteceu antes com o nome antigo "intradesk").
try {
    $souAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $souAdmin) {
        Write-Host "AVISO IMPORTANTE: este script nao esta rodando como Administrador -- o nome 'infradesk' NAO sera configurado no arquivo hosts. Rode onboarding-notebook-admin.bat (ou 'Executar como administrador') para que o link http://infradesk:3000 funcione neste notebook." -ForegroundColor Red
    } else {
        $ipParaInfradesk = "192.168.1.87"
        $testeLan = Test-NetConnection -ComputerName "192.168.1.87" -Port 8000 -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
        if (-not $testeLan.TcpTestSucceeded) {
            $tailscaleExe = "C:\Program Files\Tailscale\tailscale.exe"
            if (Test-Path $tailscaleExe) {
                $ipParaInfradesk = "100.95.222.38"
            }
        }

        $hostsPath = Join-Path $env:WinDir "System32\drivers\etc\hosts"
        $conteudoHosts = Get-Content -Path $hostsPath -Raw -ErrorAction SilentlyContinue
        if (-not $conteudoHosts -or $conteudoHosts -notmatch '(?im)^\s*\d{1,3}(\.\d{1,3}){3}\s+infradesk\s*$') {
            Add-Content -Path $hostsPath -Value "`n$ipParaInfradesk`tinfradesk" -Encoding ASCII
            Write-Host "Nome 'infradesk' adicionado ao arquivo hosts (aponta para $ipParaInfradesk)." -ForegroundColor Green
        }
    }
} catch {
    Write-Host "AVISO IMPORTANTE: nao foi possivel configurar o nome 'infradesk' no arquivo hosts ($($_.Exception.Message)) -- o link http://infradesk:3000 nao vai funcionar neste notebook." -ForegroundColor Red
}

$destinoExe = Join-Path $installDir "Agente_manual.exe"
Copy-Item -Path $CaminhoAgente -Destination $destinoExe -Force

$vinculo = @{
    usuario = $Usuario
    patrimonio = $PatrimonioNotebook
    patrimonio_monitor = $PatrimonioTela
}

$vinculo | ConvertTo-Json | Set-Content -Path (Join-Path $configDir "agente_manual_vinculo.json") -Encoding UTF8

function Get-InteractiveUser {
    # $env:USERNAME reflete quem elevou o processo (pode ser uma conta admin
    # diferente do usuario logado no notebook). Aqui detectamos o usuario da
    # sessao interativa de verdade, para a tarefa disparar no logon dele.
    try {
        $quserOutput = quser 2>$null
        if ($LASTEXITCODE -eq 0 -and $quserOutput) {
            $sessLines = $quserOutput | Select-Object -Skip 1
            $ativo = $sessLines | Where-Object { $_ -match '\bconsole\b' } | Where-Object { $_ -match '\bAtiv[oa]\b|\bActive\b' }
            if (-not $ativo) {
                $ativo = $sessLines | Where-Object { $_ -match '\bAtiv[oa]\b|\bActive\b' } | Select-Object -First 1
            }
            if ($ativo) {
                $nome = ($ativo.Trim() -split '\s+')[0].TrimStart('>')
                if (-not [string]::IsNullOrWhiteSpace($nome)) {
                    return $nome
                }
            }
        }
    } catch {}

    try {
        $cs = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
        if ($cs.UserName) {
            return ($cs.UserName -split '\\')[-1]
        }
    } catch {}

    return $env:USERNAME
}

if ($ConfigurarAutoStart) {
    $taskName = "InventarioTI - Agente_manual"
    $usuarioAlvo = Get-InteractiveUser
    if ($usuarioAlvo -ne $env:USERNAME) {
        Write-Host "Aviso: processo elevado como '$env:USERNAME', mas a tarefa sera registrada para o usuario logado na sessao: '$usuarioAlvo'." -ForegroundColor Yellow
    }
    $action = New-ScheduledTaskAction -Execute $destinoExe
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $principal = New-ScheduledTaskPrincipal -UserId $usuarioAlvo -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

    try {
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        Write-Host "Auto start configurado: $taskName (usuario: $usuarioAlvo)" -ForegroundColor Green
    } catch {
        Write-Host "Aviso: nao foi possivel registrar a tarefa agendada ($($_.Exception.Message))" -ForegroundColor Yellow
        Write-Host "Verifique se o servico 'Agendador de Tarefas' (Schedule) esta em execucao neste notebook (Start-Service Schedule) e rode o script novamente para configurar o auto start." -ForegroundColor Yellow
    }

    # Tarefa elevada opcional pra comandos "modo admin" da aba Comandos: roda
    # como SYSTEM (sem senha nenhuma guardada, SYSTEM nao tem senha) e fica
    # monitorando uma pasta em busca de comando pra rodar com privilegio
    # total. O agente (sem privilegio, de proposito) fala com ela por arquivo
    # porque um processo sem privilegio nao consegue se autoelevar sem prompt
    # de UAC.
    $adminBridge = Join-Path $base "admin-bridge"
    # Recria do zero: se uma tentativa anterior deixou essa pasta com uma ACL
    # inconsistente/travada (ex: heranca ja removida sem os grants seguintes
    # terem sido aplicados), remover e recriar evita herdar esse estado.
    if (Test-Path $adminBridge) {
        Remove-Item -Path $adminBridge -Recurse -Force -ErrorAction SilentlyContinue
    }
    New-Item -Path $adminBridge -ItemType Directory -Force | Out-Null

    # Remove a heranca do ICACLS amplo aplicado acima em $base (Usuarios
    # Autenticados: Modify) e restringe essa subpasta especifica só ao
    # usuario deste notebook + SYSTEM/Administradores. Sem isso, qualquer
    # outra conta autenticada na maquina poderia escrever um comando aqui
    # e a tarefa SYSTEM executaria com privilegio total.
    icacls $adminBridge /inheritance:r /C /Q | Out-Null
    icacls $adminBridge /grant "SYSTEM:(OI)(CI)F" /C /Q | Out-Null
    icacls $adminBridge /grant "*S-1-5-32-544:(OI)(CI)F" /C /Q | Out-Null
    icacls $adminBridge /grant "${usuarioAlvo}:(OI)(CI)M" /C /Q | Out-Null

    # icacls e um programa externo que retorna codigo de saida 0 mesmo quando
    # falha (ex: "falha no processamento de 1 arquivos" ainda sai com exit 0)
    # -- nao da pra confiar nisso pra saber se funcionou. Confirma de verdade
    # lendo a ACL de volta com Get-Acl (cmdlet com tratamento de erro confiavel).
    try {
        $acl = Get-Acl -Path $adminBridge -ErrorAction Stop
        $heriancaRemovida = $acl.AreAccessRulesProtected
        # Compara por SID, nao pelo nome de exibicao -- em Windows em
        # portugues (como este), a conta SYSTEM aparece como "AUTORIDADE
        # NT\SISTEMA", entao um match pela string em ingles "SYSTEM" nunca
        # bateria mesmo com a permissao aplicada corretamente.
        $sidsNaAcl = $acl.Access | ForEach-Object {
            try { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value } catch { $null }
        }
        $temSystem = $sidsNaAcl -contains 'S-1-5-18'
        $temUsuarioAlvo = [bool]($acl.Access | Where-Object { $_.IdentityReference -match [regex]::Escape($usuarioAlvo) })

        if ($heriancaRemovida -and $temSystem -and $temUsuarioAlvo) {
            Write-Host "Pasta de comandos elevados restrita ao usuario $usuarioAlvo (+ SYSTEM/Administradores)." -ForegroundColor Green
        } else {
            Write-Host "Aviso: a ACL de $adminBridge nao ficou como esperado (heranca removida: $heriancaRemovida, SYSTEM: $temSystem, ${usuarioAlvo}: $temUsuarioAlvo). Comandos 'modo admin' podem nao funcionar nesta maquina ate isso ser resolvido." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Aviso: nao foi possivel verificar a ACL de $adminBridge ($($_.Exception.Message))" -ForegroundColor Yellow
    }

    $scriptAdminOrigem = Join-Path $PSScriptRoot "executar_comando_admin.ps1"
    if (Test-Path $scriptAdminOrigem) {
        $scriptAdminDestino = Join-Path $installDir "executar_comando_admin.ps1"
        Copy-Item -Path $scriptAdminOrigem -Destination $scriptAdminDestino -Force

        $taskNameAdmin = "InventarioTI - Comando Admin"
        $actionAdmin = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptAdminDestino`""
        # O Agendador de Tarefas do Windows só aceita repetição em granularidade
        # de MINUTOS -- um intervalo em segundos (ex: 20s) produz um XML de
        # tarefa inválido ("Interval:PT20S fora do intervalo permitido") e o
        # registro falha silenciosamente sempre, em qualquer máquina. 1 minuto
        # ainda deixa bastante folga dentro do timeout de 300s do lado do agente.
        # [TimeSpan]::MaxValue também é inválido pra duração (excede o que o
        # XML consegue representar) -- 10 anos já é "pra sempre" na prática.
        $triggerAdmin = New-ScheduledTaskTrigger -Once -At (Get-Date) `
            -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
        $principalAdmin = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        # Sem -AllowStartIfOnBatteries/-DontStopIfGoingOnBatteries, o
        # New-ScheduledTaskSettingsSet cria a tarefa com a condicao padrao
        # "iniciar so com o notebook na tomada" -- num parque de notebooks
        # rodando na bateria na maioria do tempo, isso faz a tarefa registrar
        # com sucesso e nunca disparar (fica "Ready" pra sempre, LastRunTime
        # nunca preenchido), sem erro nenhum visivel no onboarding.
        $settingsAdmin = New-ScheduledTaskSettingsSet `
            -StartWhenAvailable `
            -MultipleInstances IgnoreNew `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

        try {
            Register-ScheduledTask -TaskName $taskNameAdmin -Action $actionAdmin -Trigger $triggerAdmin -Principal $principalAdmin -Settings $settingsAdmin -Force | Out-Null
            Write-Host "Tarefa elevada configurada: $taskNameAdmin (roda como SYSTEM, verifica a cada 1 min)" -ForegroundColor Green
        } catch {
            Write-Host "Aviso: nao foi possivel registrar a tarefa elevada de comandos admin ($($_.Exception.Message))" -ForegroundColor Yellow
            Write-Host "Comandos 'modo admin' nao vao funcionar nesta maquina ate isso ser resolvido (comandos normais continuam ok)." -ForegroundColor Yellow
        }
    } else {
        Write-Host "Aviso: executar_comando_admin.ps1 nao encontrado ao lado do onboarding; comandos 'modo admin' nao estarao disponiveis nesta maquina." -ForegroundColor Yellow
    }
}

Write-Host "Executando agente uma vez para validacao inicial..." -ForegroundColor Cyan
$argList = @()
if ($ForcarCadastro) { $argList += '--forcar' }

$procParams = @{
    FilePath = $destinoExe
    PassThru = $true
    WindowStyle = 'Hidden'
}
if ($argList.Count -gt 0) {
    $procParams.ArgumentList = $argList
}

$proc = Start-Process @procParams
Start-Sleep -Seconds 12
if (-not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}

$logFile = Join-Path $logDir "agente_manual.log"
if (Test-Path $logFile) {
    Write-Host "Ultimas linhas do log:" -ForegroundColor Yellow
    Get-Content $logFile -Tail 10
}

Write-Host "Onboarding concluido para usuario $Usuario" -ForegroundColor Green
Write-Host "Valide no painel de monitoramento: ultimo contato, status online/offline e pendencias de envio." -ForegroundColor White
