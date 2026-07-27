from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class DiseasePhoto(Base):
    __tablename__ = "disease_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True, default="local_demo")
    original_name: Mapped[str] = mapped_column(String(260), default="")
    stored_name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    relative_path: Mapped[str] = mapped_column(String(420), unique=True)
    mime_type: Mapped[str] = mapped_column(String(80), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    analysis_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
