import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import require_roles
from app.core.rate_limit import limiter
from app.crud import audit_log
from app.models.audit_log import AuditLog

router = APIRouter()


def _parse_json_field(raw_value: str | None) -> dict[str, Any] | None:
    if not raw_value:
        return None
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _to_payload(event: AuditLog) -> dict[str, Any]:
    return {
        "id": event.id,
        "actor_email": event.actor_email,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "details": event.details,
        "old_values": _parse_json_field(event.old_values),
        "new_values": _parse_json_field(event.new_values),
        "ip_address": event.ip_address,
        "user_agent": event.user_agent,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


@router.get("")
@limiter.limit("60/minute")
def list_audit_events(
    request: Request,
    db: Session = Depends(get_db),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    actor_email: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _current_user=Depends(require_roles("admin", "manager", "viewer")),
) -> list[dict[str, Any]]:
    if action:
        events = audit_log.get_action_logs(db, action=action, limit=limit)
    else:
        events = audit_log.list_recent_events(db, limit=limit, entity_type=entity_type, actor_email=actor_email)
    return [_to_payload(event) for event in events]


@router.get("/pending")
@limiter.limit("60/minute")
def list_pending_audit_events(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=200),
    _current_user=Depends(require_roles("admin", "manager", "viewer")),
) -> list[dict[str, Any]]:
    events = audit_log.list_pending_events(db, limit=limit)
    return [_to_payload(event) for event in events]


@router.post("/pending/{event_id}/resolve")
@limiter.limit("30/minute")
def resolve_pending_audit_event(
    request: Request,
    event_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager")),
) -> dict[str, Any]:
    audit_log.resolve_pending_event(db, event_id, resolved_by=current_user.email, notes="resolved-via-api")
    return {"status": "resolved", "event_id": event_id}


@router.post("/pending/resolve-all")
@limiter.limit("10/minute")
def resolve_all_pending_audit_events(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager")),
) -> dict[str, Any]:
    total = audit_log.resolve_all_pending_events(db, resolved_by=current_user.email, notes="resolved-via-api")
    return {"status": "resolved", "total": total}
