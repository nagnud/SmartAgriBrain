from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AppState(Base):
    __tablename__ = "app_states"
    __table_args__ = (UniqueConstraint("user_id", "state_key", name="uq_app_state_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(80), index=True, default="local_demo")
    state_key: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
