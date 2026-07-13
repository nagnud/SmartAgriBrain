from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def utc_now() -> datetime:
    return datetime.utcnow()


class TelemetryReceipt(Base):
    __tablename__ = "telemetry_receipts"
    __table_args__ = (
        UniqueConstraint("device_id", "message_id", name="uq_telemetry_receipt_device_message"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    telemetry_record_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("telemetry_records.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    transport: Mapped[str] = mapped_column(String(16), nullable=False, default="http")
    normalized_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    received_at: Mapped[int] = mapped_column(BigInteger, nullable=False)


class DevicePresence(Base):
    __tablename__ = "device_presence"

    device_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    transport: Mapped[str] = mapped_column(String(16), nullable=False, default="http")
    last_seen_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_telemetry_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class DeviceAlarmSetting(Base):
    __tablename__ = "device_alarm_settings"
    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_alarm_setting_user_device"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(80), nullable=False, default="local_demo", index=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    ranges: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class AlarmRecord(Base):
    __tablename__ = "alarms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(80), nullable=False, default="local_demo", index=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    rule_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    metric_key: Mapped[str | None] = mapped_column(String(48), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(12), nullable=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="环境监测")
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    opened_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    handled_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resolved_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class AlarmRuleState(Base):
    __tablename__ = "alarm_rule_states"
    __table_args__ = (
        UniqueConstraint("user_id", "device_id", "rule_key", name="uq_alarm_rule_user_device_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(80), nullable=False, default="local_demo", index=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    rule_key: Mapped[str] = mapped_column(String(80), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(12), nullable=True)
    abnormal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_alarm_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
