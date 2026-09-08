from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.backup_session import BackupBase


class BackupLog(BackupBase):
    __tablename__ = "backup_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="em_andamento", index=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(20))
    triggered_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
