from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class SiteSnapshotRecord(Base):
    __tablename__ = "site_snapshots"
    __table_args__ = (Index("ix_site_snapshot_site_time", "site_id", "sampled_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    sampled_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    received_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class SiteHistorySample(Base):
    """One real site reading per ten seconds, retained for the dashboard history view."""

    __tablename__ = "site_history_samples"
    __table_args__ = (
        UniqueConstraint("site_id", "bucket_at", name="uq_site_history_sample_bucket"),
        Index("ix_site_history_sample_site_time", "site_id", "sampled_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    bucket_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    sampled_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    received_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class EdgeDeviceRecord(Base):
    __tablename__ = "edge_devices"

    device_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class SiteCommandRecord(Base):
    __tablename__ = "site_commands"
    __table_args__ = (Index("ix_site_command_queue", "device_id", "state", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    command_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    site_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    assistant_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dispatched_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    acknowledged_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class EdgeAssistantSession(Base):
    __tablename__ = "edge_assistant_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(24), nullable=False, default="edge")
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)


class EdgeAssistantMessage(Base):
    __tablename__ = "edge_assistant_messages"
    __table_args__ = (Index("ix_edge_assistant_message_session_time", "session_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class EdgeAssistantAction(Base):
    __tablename__ = "edge_assistant_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    risk: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    resolved_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
