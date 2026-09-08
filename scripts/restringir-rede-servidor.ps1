param(
    # 100.64.0.0/10 é a faixa CGNAT que o Tailscale usa pros IPs da rede
    # privada dele -- só quem estiver no mesmo tailnet consegue ter um IP
    # nessa faixa, então liberar isso não expõe a porta pra internet.
    [string[]]$AllowedSubnets = @("192.168.1.0/24", "192.168.8.0/24", "100.64.0.0/10"),
    [int[]]$Ports = @(8000, 5000, 3000)
)

$ErrorActionPreference = "Stop"

foreach ($port in $Ports) {
    $allowName = "Inventario-Allow-$port"
    $blockName = "Inventario-Block-$port"

    Get-NetFirewallRule -DisplayName $allowName -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    # A regra de bloqueio "Any" era redundante -- o Windows já bloqueia por
    # padrão qualquer porta sem uma regra explícita de liberação, e ter as
    # duas juntas no mesmo escopo cria ambiguidade de prioridade entre elas.
    # Mantém a limpeza aqui só por compatibilidade com quem já rodou a versão antiga.
    Get-NetFirewallRule -DisplayName $blockName -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue

    New-NetFirewallRule -DisplayName $allowName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -RemoteAddress $AllowedSubnets -ErrorAction Stop | Out-Null

    Write-Host "Regra aplicada para porta $port" -ForegroundColor Green
}

Write-Host "Restricao de rede aplicada para portas: $($Ports -join ', ')" -ForegroundColor Cyan
Write-Host "Sub-redes permitidas: $($AllowedSubnets -join ', ')" -ForegroundColor White
