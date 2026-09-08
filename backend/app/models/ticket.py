from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero_serie: Mapped[str | None] = mapped_column(String(120), index=True)
    usuario: Mapped[str | None] = mapped_column(String(120))
    patrimonio: Mapped[str | None] = mapped_column(String(64))
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    categoria: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default="aberto", nullable=False)
    resposta: Mapped[str | None] = mapped_column(Text)
    respondido_por: Mapped[str | None] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
