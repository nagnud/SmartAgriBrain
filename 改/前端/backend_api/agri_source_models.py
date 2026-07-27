from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AgriSourceSetting(Base):
    __tablename__ = "agri_source_settings"

    source_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
