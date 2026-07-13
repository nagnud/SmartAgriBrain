from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Float, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TelemetryRecord(Base):
    __tablename__ = "telemetry_records"
    __table_args__ = (Index("ix_telemetry_device_timestamp", "device_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    humidity: Mapped[float] = mapped_column(Float, nullable=False)
    pressure: Mapped[float] = mapped_column(Float, nullable=False)
    gas_resistance: Mapped[float] = mapped_column(Float, nullable=False)
    light: Mapped[float] = mapped_column(Float, nullable=False)
    co2: Mapped[float] = mapped_column(Float, nullable=False)
    soil_moisture: Mapped[float] = mapped_column(Float, nullable=False)
    soil_ec: Mapped[float] = mapped_column(Float, nullable=False)

    wifi: Mapped[str] = mapped_column(String(24), nullable=False)
    mqtt: Mapped[str] = mapped_column(String(24), nullable=False)
    fan: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pump: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    light_status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alarm: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    curtain: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    received_at: Mapped[int] = mapped_column(BigInteger, nullable=False)


class DeviceCommandRecord(Base):
    __tablename__ = "device_commands"
    __table_args__ = (Index("ix_device_command_queue", "device_id", "status", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    command: Mapped[str] = mapped_column(String(48), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dispatched_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    executed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    execution_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    result_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reported_status: Mapped[dict | None] = mapped_column(JSON, nullable=True)
