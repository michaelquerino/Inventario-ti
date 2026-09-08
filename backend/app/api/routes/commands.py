import sys
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import require_roles
from app.core.agent_connections import agent_connections
from app.core.audit_utils import get_client_ip, get_user_agent
from app.core.legacy_db import repo_root as _repo_root
from app.core.rate_limit import limiter
from app.crud import audit_log
from app.models.legacy import Comando, ComandoTemplate
from app.schemas.command import CommandCreate, CommandRead, CommandTemplateCreate, CommandTemplateRead

router = APIRouter()


def _load_root_config():
    repo_root = str(_repo_root())
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    import config  # config.py na raiz do repositório (usado pelo agente/servidor)

    return config


def _build_agent_update_script(enderecos: list[str], porta: int, api_key: str) -> str:
    urls = ", ".join(f"'http://{ip}:{porta}/agente/download'" for ip in enderecos)
    return f"""$ErrorActionPreference = 'Stop'
$base = Join-Path $env:ProgramData 'InventarioTI'
$dest = Join-Path $base 'Agente_manual.exe'
$novo = Join-Path $base 'Agente_manual.novo.exe'
$apiKey = '{api_key}'
$urls = @({urls})
$ok = $false
foreach ($url in $urls) {{
    try {{
        Invoke-WebRequest -Uri $url -Headers @{{ 'X-API-Key' = $apiKey }} -OutFile $novo -UseBasicParsing -TimeoutSec 30
        $ok = $true
        break
    }} catch {{
        Write-Host "Falhou em $url : $($_.Exception.Message)"
    }}
}}
if (-not $ok) {{ throw 'Nao foi possivel baixar a nova versao do agente em nenhum endereco do servidor.' }}
if ((Get-Item $novo).Length -lt 1000000) {{ throw 'Arquivo baixado parece invalido (tamanho muito pequeno).' }}

$watcherScript = @"
Start-Sleep -Seconds 5
Stop-ScheduledTask -TaskName 'InventarioTI - Agente_manual' -ErrorAction SilentlyContinue
Get-Process -Name 'Agente_manual' -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Move-Item -Path '$novo' -Destination '$dest' -Force
Start-ScheduledTask -TaskName 'InventarioTI - Agente_manual'
"@
$watcherPath = Join-Path $base 'atualizar_agente.ps1'
Set-Content -Path $watcherPath -Value $watcherScript -Encoding UTF8
Start-Process powershell -ArgumentList @('-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File', $watcherPath) -WindowStyle Hidden

'Atualizacao agendada: nova versao sera aplicada em ~7s (o agente sera reiniciado automaticamente).'
"""


def _comando_to_dict(comando: Comando) -> dict:
    return {
        "id": comando.id,
        "numero_serie": comando.numero_serie,
        "comando": comando.comando,
        "status": comando.status,
        "resultado": comando.resultado,
        "codigo_saida": comando.codigo_saida,
        "criado_por": comando.criado_por,
        "criado_em": comando.criado_em,
        "executado_em": comando.executado_em,
        "agendado_para": comando.agendado_para,
        # Comandos antigos (de antes da coluna existir) podem ter modo NULL.
        "modo": comando.modo or "usuario",
    }


def _template_to_dict(template: ComandoTemplate) -> dict:
    return {
        "id": template.id,
        "nome": template.nome,
        "comando": template.comando,
        "criado_por": template.criado_por,
        "criado_em": template.criado_em,
    }


# Apenas admin pode ver e criar comandos remotos: é execução de código na
# frota inteira de notebooks, então fica restrito ao dono do sistema.
@router.post("", response_model=list[CommandRead], status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_command(
    request: Request,
    payload: CommandCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin")),
) -> list[dict]:
    numero_series = [n.strip() for n in payload.numero_series if n.strip()]
    comando = payload.comando.strip()
    agendado_para = (payload.agendado_para or "").strip() or None

    if not numero_series or not comando:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="numero_series e comando são obrigatórios")

    if agendado_para:
        try:
            datetime.fromisoformat(agendado_para)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="agendado_para inválido") from exc

    criado_em = datetime.now().isoformat()
    criados: list[dict] = []
    for numero_serie in numero_series:
        novo_comando = Comando(
            numero_serie=numero_serie,
            comando=comando,
            status="pendente",
            criado_por=current_user.email,
            criado_em=criado_em,
            agendado_para=agendado_para,
            modo=payload.modo,
        )
        db.add(novo_comando)
        db.flush()  # popula novo_comando.id antes do commit no fim da função
        criados.append(_comando_to_dict(novo_comando))
    db.commit()

    # Empurra na hora pros notebooks que estiverem conectados via WebSocket;
    # se algum não estiver (ainda no polling antigo, ou temporariamente
    # offline), o comando já está salvo como 'pendente' e será pego no
    # próximo checkin/handshake normalmente -- isso aqui é só o atalho rápido.
    for comando in criados:
        agent_connections.notify_threadsafe(
            comando["numero_serie"],
            {"type": "command", "id": comando["id"], "comando": comando["comando"], "modo": comando["modo"]},
        )

    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="command.create" if payload.modo != "admin" else "command.create_admin",
        entity_type="command",
        entity_id=",".join(str(c["id"]) for c in criados),
        details=f"{len(numero_series)} notebook(s) [modo={payload.modo}]: {comando}"
        + (f" (agendado para {agendado_para})" if agendado_para else ""),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    return criados


@router.get("", response_model=list[CommandRead])
@limiter.limit("60/minute")
def list_commands(
    request: Request,
    db: Session = Depends(get_db),
    numero_serie: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _current_user=Depends(require_roles("admin")),
) -> list[dict]:
    statement = select(Comando).order_by(Comando.id.desc()).limit(limit)
    if numero_serie:
        statement = statement.where(Comando.numero_serie == numero_serie.strip())

    comandos = db.scalars(statement).all()
    return [_comando_to_dict(comando) for comando in comandos]


# Só deixa excluir comandos ainda pendentes: um comando que já começou a
# rodar ou já terminou fica no histórico (excluir um "executando"/"concluido"
# apagaria um resultado de verdade, inclusive o de um comando admin que já
# tenha feito alguma alteração no notebook).
@router.delete("/{command_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def delete_command(
    request: Request,
    command_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin")),
) -> None:
    comando = db.get(Comando, command_id)
    if comando is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comando não encontrado")
    if comando.status != "pendente":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Só é possível excluir comandos ainda pendentes",
        )

    numero_serie, texto_comando = comando.numero_serie, comando.comando
    db.delete(comando)
    db.commit()

    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="command.delete",
        entity_type="command",
        entity_id=str(command_id),
        details=f"numero_serie={numero_serie}: {texto_comando}",
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


# Cancela um comando preso em 'pendente' ou 'executando' (ex: o notebook
# ficou offline/travado no meio, ou a tarefa admin nunca respondeu) sem
# apagar o registro do histórico -- diferente do DELETE, aqui fica marcado
# como 'erro' com uma nota, então o operador ainda vê que aquele comando
# existiu e foi cancelado manualmente, em vez de simplesmente sumir.
@router.patch("/{command_id}/cancel", response_model=CommandRead)
@limiter.limit("30/minute")
def cancel_command(
    request: Request,
    command_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin")),
) -> dict:
    comando = db.get(Comando, command_id)
    if comando is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comando não encontrado")
    if comando.status not in ("pendente", "executando"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Só é possível cancelar comandos pendentes ou em execução",
        )

    numero_serie, texto_comando = comando.numero_serie, comando.comando
    comando.status = "erro"
    comando.resultado = "Cancelado manualmente pelo administrador."
    comando.executado_em = datetime.now().isoformat()
    db.add(comando)
    db.commit()

    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="command.cancel",
        entity_type="command",
        entity_id=str(command_id),
        details=f"numero_serie={numero_serie}: {texto_comando}",
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    return _comando_to_dict(comando)


# Gera um script pronto que baixa o executável mais recente do servidor
# (rota /agente/download, agora servida pelo próprio backend FastAPI -- veja
# api/routes/agent_ws.py -- em vez do Flask/servidor.py) e o troca no
# notebook. Fica pronto para colar/editar no campo de comando; nada é
# executado a partir daqui.
@router.get("/agent-update-script")
@limiter.limit("30/minute")
def get_agent_update_script(
    request: Request,
    _current_user=Depends(require_roles("admin")),
) -> dict:
    cfg = _load_root_config()
    enderecos = [ip for ip in getattr(cfg, "ENDERECOS_SERVIDOR", []) if ip]
    if not enderecos:
        raise HTTPException(status_code=500, detail="Nenhum endereço de servidor configurado em config.py")

    porta_backend = getattr(cfg, "PORTA_BACKEND_WS", 8000)
    script = _build_agent_update_script(enderecos, porta_backend, cfg.API_KEY_AGENTE)
    return {"script": script}


# Biblioteca de comandos salvos: templates reutilizáveis (nome + texto do
# comando) pra não precisar redigitar/colar comandos repetidos toda vez.
@router.post("/templates", response_model=CommandTemplateRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_command_template(
    request: Request,
    payload: CommandTemplateCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin")),
) -> dict:
    nome = payload.nome.strip()
    comando = payload.comando.strip()
    if not nome or not comando:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="nome e comando são obrigatórios")

    novo_template = ComandoTemplate(
        nome=nome,
        comando=comando,
        criado_por=current_user.email,
        criado_em=datetime.now().isoformat(),
    )
    db.add(novo_template)
    db.commit()
    db.refresh(novo_template)

    return _template_to_dict(novo_template)


@router.get("/templates", response_model=list[CommandTemplateRead])
@limiter.limit("60/minute")
def list_command_templates(
    request: Request,
    db: Session = Depends(get_db),
    _current_user=Depends(require_roles("admin")),
) -> list[dict]:
    statement = select(ComandoTemplate).order_by(ComandoTemplate.nome.collate("NOCASE").asc())
    templates = db.scalars(statement).all()
    return [_template_to_dict(template) for template in templates]


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def delete_command_template(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(require_roles("admin")),
) -> None:
    template = db.get(ComandoTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comando salvo não encontrado")
    db.delete(template)
    db.commit()
