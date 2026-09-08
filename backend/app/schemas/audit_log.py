from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditLogRead(BaseModel):
    """Modelo para leitura de logs de auditoria"""

    id: int
    actor_email: str | None = None
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    details: str | None = None
    old_values: dict[str, Any] | None = Field(None, description="JSON com valores anteriores")
    new_values: dict[str, Any] | None = Field(None, description="JSON com valores novos")
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogFilter(BaseModel):
    """Filtros para buscar logs de auditoria"""

    entity_type: str | None = None
    actor_email: str | None = None
    action: str | None = None
    limit: int = 50


class AuditSummary(BaseModel):
    """Resumo de atividade de auditoria"""

    total_events: int
    events_by_action: dict[str, int]
    most_recent_logs: list[AuditLogRead]

