from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset_tag: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    screen_asset_tag: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(120))
    owner: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

