import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import require_roles
from app.core.agent_connections import agent_connections
from app.core.audit_utils import get_client_ip, get_user_agent
from app.core.rate_limit import limiter
from app.crud import audit_log
from app.schemas.command import CommandCreate, CommandRead, CommandTemplateCreate, CommandTemplateRead

router = APIRouter()


def _repo_root() -> Path:
    # backend/app/api/routes/commands.py -> repo root
    return Path(__file__).resolve().parents[4]


def _legacy_db_path() -> Path:
    # ativos.db e inventario.db foram unificados num arquivo só -- as tabelas
    # 'comandos'/'comando_templates' agora moram dentro de inventario.db.
    return _repo_root() / "inventario.db"


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


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comandos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_serie TEXT NOT NULL,
            comando TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            resultado TEXT,
            codigo_saida INTEGER,
            criado_por TEXT,
            criado_em TEXT NOT NULL,
            executado_em TEXT
        )
        """
    )
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(comandos)").fetchall()}
    if "agendado_para" not in existing_columns:
        conn.execute("ALTER TABLE comandos ADD COLUMN agendado_para TEXT")
    if "modo" not in existing_columns:
        conn.execute("ALTER TABLE comandos ADD COLUMN modo TEXT")


def _row_to_command(row: tuple) -> dict:
    return {
        "id": row[0],
        "numero_serie": row[1],
        "comando": row[2],
        "status": row[3],
        "resultado": row[4],
        "codigo_saida": row[5],
        "criado_por": row[6],
        "criado_em": row[7],
        "executado_em": row[8],
        "agendado_para": row[9],
        "modo": row[10] or "usuario",
    }


_SELECT_COMMAND = """
    SELECT id, numero_serie, comando, status, resultado, codigo_saida, criado_por, criado_em, executado_em, agendado_para, modo
    FROM comandos
"""


def _ensure_templates_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS comando_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            comando TEXT NOT NULL,
            criado_por TEXT,
            criado_em TEXT NOT NULL
        )
        """
    )


def _row_to_template(row: tuple) -> dict:
    return {
        "id": row[0],
        "nome": row[1],
        "comando": row[2],
        "criado_por": row[3],
        "criado_em": row[4],
    }


_SELECT_TEMPLATE = "SELECT id, nome, comando, criado_por, criado_em FROM comando_templates"


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

    legacy_db = _legacy_db_path()
    criado_em = datetime.now().isoformat()
    criados: list[dict] = []
    with sqlite3.connect(legacy_db) as conn:
        _ensure_table(conn)
        for numero_serie in numero_series:
            cursor = conn.execute(
                """
                INSERT INTO comandos (numero_serie, comando, status, criado_por, criado_em, agendado_para, modo)
                VALUES (?, ?, 'pendente', ?, ?, ?, ?)
                """,
                (numero_serie, comando, current_user.email, criado_em, agendado_para, payload.modo),
            )
            novo_id = cursor.lastrowid
            row = conn.execute(f"{_SELECT_COMMAND} WHERE id = ?", (novo_id,)).fetchone()
            criados.append(_row_to_command(row))
        conn.commit()

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
    numero_serie: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _current_user=Depends(require_roles("admin")),
) -> list[dict]:
    legacy_db = _legacy_db_path()
    if not legacy_db.exists():
        return []

    with sqlite3.connect(legacy_db) as conn:
        _ensure_table(conn)
        if numero_serie:
            rows = conn.execute(
                f"{_SELECT_COMMAND} WHERE numero_serie = ? ORDER BY id DESC LIMIT ?",
                (numero_serie.strip(), limit),
            ).fetchall()
        else:
            rows = conn.execute(f"{_SELECT_COMMAND} ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    return [_row_to_command(row) for row in rows]


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
    legacy_db = _legacy_db_path()
    with sqlite3.connect(legacy_db) as conn:
        _ensure_table(conn)
        row = conn.execute(f"{_SELECT_COMMAND} WHERE id = ?", (command_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comando não encontrado")
        if row[3] != "pendente":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Só é possível excluir comandos ainda pendentes",
            )
        conn.execute("DELETE FROM comandos WHERE id = ?", (command_id,))
        conn.commit()

    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="command.delete",
        entity_type="command",
        entity_id=str(command_id),
        details=f"numero_serie={row[1]}: {row[2]}",
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
    legacy_db = _legacy_db_path()
    with sqlite3.connect(legacy_db) as conn:
        _ensure_table(conn)
        row = conn.execute(f"{_SELECT_COMMAND} WHERE id = ?", (command_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comando não encontrado")
        if row[3] not in ("pendente", "executando"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Só é possível cancelar comandos pendentes ou em execução",
            )
        conn.execute(
            """
            UPDATE comandos
            SET status = 'erro', resultado = ?, executado_em = ?
            WHERE id = ?
            """,
            ("Cancelado manualmente pelo administrador.", datetime.now().isoformat(), command_id),
        )
        conn.commit()
        updated_row = conn.execute(f"{_SELECT_COMMAND} WHERE id = ?", (command_id,)).fetchone()

    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="command.cancel",
        entity_type="command",
        entity_id=str(command_id),
        details=f"numero_serie={row[1]}: {row[2]}",
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    return _row_to_command(updated_row)


# Gera um script pronto que baixa o executável mais recente do servidor
# (rota /agente/download em servidor.py) e o troca no notebook. Fica pronto
# para colar/editar no campo de comando; nada é executado a partir daqui.
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

    script = _build_agent_update_script(enderecos, cfg.PORTA_SERVIDOR, cfg.API_KEY_AGENTE)
    return {"script": script}


# Biblioteca de comandos salvos: templates reutilizáveis (nome + texto do
# comando) pra não precisar redigitar/colar comandos repetidos toda vez.
@router.post("/templates", response_model=CommandTemplateRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_command_template(
    request: Request,
    payload: CommandTemplateCreate,
    current_user=Depends(require_roles("admin")),
) -> dict:
    nome = payload.nome.strip()
    comando = payload.comando.strip()
    if not nome or not comando:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="nome e comando são obrigatórios")

    legacy_db = _legacy_db_path()
    criado_em = datetime.now().isoformat()
    with sqlite3.connect(legacy_db) as conn:
        _ensure_templates_table(conn)
        cursor = conn.execute(
            "INSERT INTO comando_templates (nome, comando, criado_por, criado_em) VALUES (?, ?, ?, ?)",
            (nome, comando, current_user.email, criado_em),
        )
        novo_id = cursor.lastrowid
        row = conn.execute(f"{_SELECT_TEMPLATE} WHERE id = ?", (novo_id,)).fetchone()
        conn.commit()

    return _row_to_template(row)


@router.get("/templates", response_model=list[CommandTemplateRead])
@limiter.limit("60/minute")
def list_command_templates(
    request: Request,
    _current_user=Depends(require_roles("admin")),
) -> list[dict]:
    legacy_db = _legacy_db_path()
    if not legacy_db.exists():
        return []

    with sqlite3.connect(legacy_db) as conn:
        _ensure_templates_table(conn)
        rows = conn.execute(f"{_SELECT_TEMPLATE} ORDER BY nome COLLATE NOCASE ASC").fetchall()

    return [_row_to_template(row) for row in rows]


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def delete_command_template(
    request: Request,
    template_id: int,
    _current_user=Depends(require_roles("admin")),
) -> None:
    legacy_db = _legacy_db_path()
    with sqlite3.connect(legacy_db) as conn:
        _ensure_templates_table(conn)
        cursor = conn.execute("DELETE FROM comando_templates WHERE id = ?", (template_id,))
        conn.commit()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comando salvo não encontrado")
