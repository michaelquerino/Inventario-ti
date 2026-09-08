# Operacao Inicial Single Admin

## 1) Modo single admin

- Backend: defina SINGLE_ADMIN_MODE=true.
- Frontend: defina NEXT_PUBLIC_SINGLE_ADMIN_MODE=true e NEXT_PUBLIC_ENABLE_SELF_REGISTER=false.
- Resultado: cadastro publico bloqueado e tela de permissoes por perfil oculta.

## 2) Confiabilidade dos agentes

- O agente envia fila_pendente_local no payload.
- O painel de monitoramento exibe por notebook:
  - ultimo contato
  - status online/offline
  - pendencias de envio

## 3) Servidor sempre disponivel (Windows)

1. Abra PowerShell como Administrador na raiz do projeto.
2. Execute:

```powershell
.\scripts\install-server-autostart.ps1
```

3. O script cria a tarefa agendada Inventario-Stack-Watchdog em SYSTEM, no startup.
4. Logs de servico:
   - logs/watchdog.log
   - logs/backend-service.log
   - logs/collector-service.log

## 4) Restricao simples de rede (fase 1)

Execute no servidor (Administrador):

```powershell
.\scripts\restringir-rede-servidor.ps1 -AllowedSubnets "192.168.1.0/24","192.168.8.0/24"
```

Isso libera portas 8000 e 5000 apenas para as sub-redes permitidas.

## 5) Onboarding padronizado dos notebooks

Em cada notebook (PowerShell como Administrador):

```powershell
.\scripts\onboarding-notebook.ps1 -Usuario "NOME.USUARIO" -PatrimonioNotebook "NB-123" -PatrimonioTela "MON-456" -CaminhoAgente ".\dist\Agente_manual.exe"
```

O script:
- copia o Agente_manual.exe para ProgramData
- grava vinculo inicial
- configura auto start no logon
- executa uma validacao inicial e mostra as ultimas linhas do log

## 6) Rotina diaria

- Use o Dashboard para 3 indicadores-chave: alertas ativos, sem heartbeat e fila pendente.
- Nas telas criticas, use o botao Atualizar para confirmar estado atual.
- Mensagens de erro foram simplificadas para operacao diaria.

## 7) Fase 2 sugerida

- Migrar de chave unica para chave por dispositivo.
- Adicionar inventario de ultimo erro de envio por notebook.
- Criar job de auditoria para detectar notebooks sem heartbeat por mais de 24h.
