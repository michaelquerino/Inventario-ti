import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import require_roles
from app.core.audit_utils import get_client_ip, get_user_agent
from app.core.config import settings
from app.core.rate_limit import limiter
from app.crud import audit_log, backup
from app.models.backup_log import BackupLog
from app.schemas.backup import BackupLogRead

router = APIRouter()


def _repo_root() -> Path:
    # backend/app/api/routes/backups.py -> repo root
    return Path(__file__).resolve().parents[4]


def _to_payload(log: BackupLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "finished_at": log.finished_at.isoformat() if log.finished_at else None,
        "status": log.status,
        "file_path": log.file_path,
        "size_bytes": log.size_bytes,
        "message": log.message,
        "triggered_by": log.triggered_by,
        "triggered_by_email": log.triggered_by_email,
    }


# Backup do banco de dados (inventario.db) é restrito a admin: expõe uma
# cópia completa dos dados da empresa.
@router.post("", response_model=BackupLogRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("6/minute")
def run_backup_now(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin")),
) -> dict[str, Any]:
    log = backup.run_backup(
        triggered_by="manual",
        triggered_by_email=current_user.email,
        retention_count=settings.backup_retention_count,
    )

    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="backup.run",
        entity_type="backup",
        entity_id=str(log.id),
        details=f"status={log.status}",
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    if log.status == "erro":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=log.message or "Falha no backup")

    return _to_payload(log)


@router.get("", response_model=list[BackupLogRead])
@limiter.limit("60/minute")
def list_backups(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    _current_user=Depends(require_roles("admin")),
) -> list[dict[str, Any]]:
    logs = backup.list_backups(limit=limit)
    return [_to_payload(log) for log in logs]


@router.get("/{backup_id}/download")
@limiter.limit("20/minute")
def download_backup(
    request: Request,
    backup_id: int,
    _current_user=Depends(require_roles("admin")),
) -> FileResponse:
    log = backup.get_backup(backup_id)
    if log is None or log.status != "sucesso" or not log.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup não encontrado")

    caminho = _repo_root() / log.file_path
    if not caminho.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo de backup não existe mais no servidor")

    return FileResponse(caminho, media_type="application/zip", filename=caminho.name)


# Restaura ativos.db/inventario.db a partir de um zip exportado por esta mesma
# tela. Sempre gera um backup de segurança do estado atual antes de sobrescrever
# qualquer coisa (aparece no histórico com triggered_by='seguranca_pre_importacao').
@router.post("/import")
@limiter.limit("3/minute")
def import_backup(
    request: Request,
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    current_user=Depends(require_roles("admin")),
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_zip:
        shutil.copyfileobj(file.file, tmp_zip)
        tmp_zip_path = Path(tmp_zip.name)

    try:
        resultado = backup.restore_from_zip(
            tmp_zip_path,
            triggered_by_email=current_user.email,
            retention_count=settings.backup_retention_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        tmp_zip_path.unlink(missing_ok=True)

    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="backup.import",
        entity_type="backup",
        entity_id=str(resultado["safety_backup_id"]),
        details=f"restaurados={resultado['restored']} falhas={resultado['failed']}",
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    if resultado["failed"] and not resultado["restored"]:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="; ".join(resultado["failed"]))

    return resultado
