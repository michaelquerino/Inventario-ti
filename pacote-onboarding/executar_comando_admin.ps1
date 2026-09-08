# Executado periodicamente por uma tarefa agendada rodando como SYSTEM
# (registrada em onboarding-notebook.ps1). Existe só pra dar ao agente
# (que roda sem privilégio, de propósito) uma forma de executar comandos
# "modo admin" com privilégio total, sem precisar de prompt de UAC nem senha
# guardada em lugar nenhum.
#
# Comunicação é via arquivo, numa pasta com ACL restrita só ao usuário do
# notebook + SYSTEM/Administradores (veja onboarding-notebook.ps1). Cada
# comando usa um par de arquivos com o id no nome:
#   comando_<id>.json   -> escrito pelo agente com o comando pendente
#   resultado_<id>.json -> escrito aqui com o resultado, pro agente ler
#
# Isolar por id (em vez de um nome fixo compartilhado) evita que um comando
# preso (ex: um instalador esperando reinício pendente do Windows) impeça
# outros comandos de serem processados -- e o limite de tempo por comando
# (via Start-Job) garante que a tarefa nunca fica bloqueada num ciclo
# indefinidamente por causa de um único comando travado.

$ErrorActionPreference = 'Stop'

$base = Join-Path $env:ProgramData 'InventarioTI'
$bridge = Join-Path $base 'admin-bridge'

if (-not (Test-Path $bridge)) {
    exit 0
}

$arquivosComando = Get-ChildItem -Path $bridge -Filter 'comando_*.json' -ErrorAction SilentlyContinue
if (-not $arquivosComando) {
    exit 0
}

foreach ($arquivo in $arquivosComando) {
    try {
        $conteudo = Get-Content -Path $arquivo.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        # Arquivo corrompido/incompleto (ex: leu no meio de uma escrita) --
        # descarta e espera o agente reenviar; não tenta executar algo que
        # não parseou certo.
        Remove-Item -Path $arquivo.FullName -Force -ErrorAction SilentlyContinue
        continue
    }

    Remove-Item -Path $arquivo.FullName -Force -ErrorAction SilentlyContinue

    $comandoId = $conteudo.id
    $comandoTexto = $conteudo.comando
    if (-not $comandoTexto -or $null -eq $comandoId) {
        continue
    }

    $outputPath = Join-Path $bridge "resultado_$comandoId.json"

    $job = Start-Job -ScriptBlock {
        param($texto)
        try {
            # -EncodedCommand em vez de -Command $texto: repassar o texto
            # direto pro powershell.exe filho via -Command depende de como o
            # PowerShell monta a linha de comando do processo nativo, e isso
            # corrompe aspas duplas embutidas (ex: comandos com URLs entre
            # aspas) -- o comando chega truncado/quebrado do outro lado.
            # Codificar em Base64 evita esse problema de quoting por completo.
            $bytesComando = [System.Text.Encoding]::Unicode.GetBytes($texto)
            $comandoCodificado = [Convert]::ToBase64String($bytesComando)
            $saidaJob = & powershell.exe -NoProfile -EncodedCommand $comandoCodificado 2>&1 | Out-String
            $codigoJob = $LASTEXITCODE
            if ($null -eq $codigoJob) { $codigoJob = 0 }
        } catch {
            $saidaJob = $_.Exception.Message
            $codigoJob = 1
        }
        [PSCustomObject]@{ saida = $saidaJob; codigo = $codigoJob }
    } -ArgumentList $comandoTexto

    # 280s (um pouco abaixo dos 300s que o agente espera) -- se o próprio
    # comando travar (ex: instalador esperando reinício pendente), essa
    # tarefa não fica presa nele: desiste, tenta encerrar o job e segue pro
    # próximo arquivo/ciclo, reportando erro em vez de nunca responder.
    $concluiu = Wait-Job -Job $job -Timeout 280
    if ($concluiu) {
        $resultadoJob = Receive-Job -Job $job -ErrorAction SilentlyContinue
        if ($resultadoJob) {
            $saida = $resultadoJob.saida
            $codigo = $resultadoJob.codigo
        } else {
            $saida = 'Job concluído sem retorno utilizável.'
            $codigo = 1
        }
    } else {
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        $saida = 'Comando excedeu o tempo limite de 280s dentro da tarefa elevada (processo pode ter ficado preso -- ex: instalador esperando reinício pendente do Windows). O processo pode continuar rodando em segundo plano; verifique manualmente se necessário.'
        $codigo = 1
    }
    Remove-Job -Job $job -Force -ErrorAction SilentlyContinue

    if ($saida.Length -gt 20000) {
        $saida = $saida.Substring(0, 20000)
    }

    $resultado = [ordered]@{
        id            = $comandoId
        resultado     = $saida
        codigo_saida  = $codigo
        finalizado_em = (Get-Date).ToString('o')
    } | ConvertTo-Json -Compress

    Set-Content -Path $outputPath -Value $resultado -Encoding UTF8
}
