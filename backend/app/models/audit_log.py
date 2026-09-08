from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(120), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), index=True)
    details: Mapped[str | None] = mapped_column(Text)
    old_values: Mapped[str | None] = mapped_column(Text, comment="JSON com valores anteriores")
    new_values: Mapped[str | None] = mapped_column(Text, comment="JSON com valores novos")
    ip_address: Mapped[str | None] = mapped_column(String(45), comment="IPv4 ou IPv6")
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

