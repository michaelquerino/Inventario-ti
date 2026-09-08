import json
from datetime import datetime, timedelta

from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

PENDING_AUDIT_ACTIONS = ("auth.login_failed", "asset.delete")


def ensure_resolution_table(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS audit_log_resolutions (
                audit_log_id INTEGER PRIMARY KEY,
                resolved_at DATETIME NOT NULL,
                resolved_by VARCHAR(255),
                notes TEXT
            )
            """
        )
    )
    db.commit()


def create_event(
    db: Session,
    *,
    actor_email: str | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: str | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Criar novo evento de auditoria com suporte a diffs (antes/depois)"""
    event = AuditLog(
        actor_email=actor_email,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        old_values=json.dumps(old_values) if old_values else None,
        new_values=json.dumps(new_values) if new_values else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_recent_events(db: Session, limit: int = 50, entity_type: str | None = None, actor_email: str | None = None) -> list[AuditLog]:
    """Listar eventos recentes com filtros opcionais"""
    query = select(AuditLog)

    conditions = []
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if actor_email:
        conditions.append(AuditLog.actor_email == actor_email)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(AuditLog.created_at.desc()).limit(limit)
    return list(db.scalars(query).all())


def get_entity_history(db: Session, entity_type: str, entity_id: str) -> list[AuditLog]:
    """Obter histórico completo de uma entidade"""
    statement = (
        select(AuditLog)
        .where(and_(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id))
        .order_by(AuditLog.created_at.asc())
    )
    return list(db.scalars(statement).all())


def get_actor_activity(db: Session, actor_email: str, days: int = 7) -> list[AuditLog]:
    """Obter atividade de um usuário nos últimos N dias"""
    since = datetime.utcnow() - timedelta(days=days)
    statement = (
        select(AuditLog)
        .where(and_(AuditLog.actor_email == actor_email, AuditLog.created_at >= since))
        .order_by(AuditLog.created_at.desc())
    )
    return list(db.scalars(statement).all())


def get_action_logs(db: Session, action: str, limit: int = 50) -> list[AuditLog]:
    """Obter logs de uma ação específica (ex: 'asset.delete')"""
    statement = select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at.desc()).limit(limit)
    return list(db.scalars(statement).all())


def count_events_by_action(db: Session, start_date: datetime | None = None) -> dict[str, int]:
    """Contar eventos por tipo de ação"""
    query = select(AuditLog.action)

    if start_date:
        query = query.where(AuditLog.created_at >= start_date)

    events = db.scalars(query).all()

    counts: dict[str, int] = {}
    for action in events:
        counts[action] = counts.get(action, 0) + 1

    return counts


def get_suspicious_activity(db: Session, ip_address: str, hours: int = 1) -> list[AuditLog]:
    """Detectar atividade suspeita: mesmo IP com muitos erros (ex: login falho)"""
    since = datetime.utcnow() - timedelta(hours=hours)
    statement = (
        select(AuditLog)
        .where(and_(AuditLog.ip_address == ip_address, AuditLog.created_at >= since, AuditLog.action.contains("login")))
        .order_by(AuditLog.created_at.desc())
    )
    return list(db.scalars(statement).all())


def list_pending_events(db: Session, limit: int = 25) -> list[AuditLog]:
    ensure_resolution_table(db)
    rows = db.execute(
        text(
            """
            SELECT al.id
            FROM audit_logs al
            LEFT JOIN audit_log_resolutions ar ON ar.audit_log_id = al.id
            WHERE al.action IN ('auth.login_failed', 'asset.delete')
              AND ar.audit_log_id IS NULL
            ORDER BY al.created_at DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).fetchall()
    ids = [int(row[0]) for row in rows]
    if not ids:
        return []

    events = list(db.scalars(select(AuditLog).where(AuditLog.id.in_(ids))).all())
    events.sort(key=lambda item: item.created_at, reverse=True)
    return events


def count_pending_events(db: Session) -> int:
    ensure_resolution_table(db)
    row = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM audit_logs al
            LEFT JOIN audit_log_resolutions ar ON ar.audit_log_id = al.id
            WHERE al.action IN ('auth.login_failed', 'asset.delete')
              AND ar.audit_log_id IS NULL
            """
        )
    ).fetchone()
    return int(row[0] if row else 0)


def resolve_pending_event(db: Session, audit_log_id: int, resolved_by: str | None = None, notes: str | None = None) -> None:
    ensure_resolution_table(db)
    db.execute(
        text(
            """
            INSERT INTO audit_log_resolutions (audit_log_id, resolved_at, resolved_by, notes)
            VALUES (:audit_log_id, :resolved_at, :resolved_by, :notes)
            ON CONFLICT(audit_log_id) DO UPDATE SET
                resolved_at = excluded.resolved_at,
                resolved_by = excluded.resolved_by,
                notes = excluded.notes
            """
        ),
        {
            "audit_log_id": audit_log_id,
            "resolved_at": datetime.utcnow(),
            "resolved_by": resolved_by,
            "notes": notes,
        },
    )
    db.commit()


def resolve_all_pending_events(db: Session, resolved_by: str | None = None, notes: str | None = None) -> int:
    events = list_pending_events(db, limit=10000)
    if not events:
        return 0
    for event in events:
        resolve_pending_event(db, event.id, resolved_by=resolved_by, notes=notes)
    return len(events)

