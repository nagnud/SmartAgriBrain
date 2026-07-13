import uuid
import time
from sqlalchemy import Column, Integer, String, Float, Boolean, JSON, BigInteger, ForeignKey, UniqueConstraint
from database import Base


# 生成 13 位毫秒级时间戳的辅助函数
def current_milli_time():
    return int(time.time() * 1000)


class Device(Base):
    __tablename__ = "devices"
    device_id = Column(String(64), primary_key=True, index=True)
    created_at = Column(BigInteger, default=current_milli_time)


class DeviceCapability(Base):
    __tablename__ = "device_capabilities"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(64), ForeignKey("devices.device_id"))
    firmware_version = Column(String(32))
    firmware_target = Column(String(32))
    sensors = Column(JSON)  # 传感器能力 JSON
    actuators = Column(JSON)  # 执行器能力 JSON
    reported_at = Column(BigInteger, default=current_milli_time)


class Telemetry(Base):
    __tablename__ = "telemetry"
    record_id = Column(String(26), primary_key=True)  # 使用 ULID 或 UUID
    message_id = Column(String(36), unique=True, index=True)
    device_id = Column(String(64), ForeignKey("devices.device_id"), index=True)
    sequence = Column(Integer)
    sampled_at = Column(BigInteger)
    received_at = Column(BigInteger, default=current_milli_time, index=True)

    # 强制规范字段列
    temperature_c = Column(Float, nullable=True)
    humidity_pct = Column(Float, nullable=True)
    pressure_kpa = Column(Float, nullable=True)
    gas_resistance_ohm = Column(Float, nullable=True)
    illuminance_lux = Column(Float, nullable=True)
    co2_ppm = Column(Float, nullable=True)
    soil_moisture_pct = Column(Float, nullable=True)
    soil_ec_ms_cm = Column(Float, nullable=True)

    # 完整 JSON 快照
    payload_snapshot = Column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint('device_id', 'sampled_at', 'sequence', name='uix_telemetry_device_time_seq'),
    )


class DeviceStatus(Base):
    __tablename__ = "device_status"
    device_id = Column(String(64), ForeignKey("devices.device_id"), primary_key=True)
    online = Column(Boolean, default=False)
    last_seen_at = Column(BigInteger, default=current_milli_time)
    last_telemetry_at = Column(BigInteger)
    connectivity = Column(JSON)  # wifi, mqtt, rssi_dbm
    actuators = Column(JSON)


class Command(Base):
    __tablename__ = "commands"
    command_id = Column(String(36), primary_key=True)
    device_id = Column(String(64), ForeignKey("devices.device_id"), index=True)
    state = Column(String(32))  # QUEUED, PUBLISHED, EXECUTED, REJECTED, EXPIRED, DELIVERY_FAILED, TIMED_OUT
    source = Column(String(32))
    reason = Column(String(255))
    operation = Column(String(32))
    target = Column(String(32))
    value = Column(Integer)
    created_at = Column(BigInteger, default=current_milli_time)
    published_at = Column(BigInteger, nullable=True)
    completed_at = Column(BigInteger, nullable=True)


class CommandAck(Base):
    __tablename__ = "command_acks"
    command_id = Column(String(36), ForeignKey("commands.command_id"), primary_key=True)
    device_id = Column(String(64))
    acknowledged_at = Column(BigInteger)
    state = Column(String(32))  # executed, rejected
    actual_value = Column(Integer, nullable=True)
    error_code = Column(String(64), nullable=True)
    full_payload = Column(JSON)


class Analysis(Base):
    __tablename__ = "analyses"
    analysis_id = Column(String(26), primary_key=True)
    device_id = Column(String(64), ForeignKey("devices.device_id"), index=True)
    crop = Column(String(64))
    risk_level = Column(String(16))  # low, medium, high
    risk_score = Column(Integer)
    risk_status = Column(String(64))
    summary = Column(String(1024))
    risk_factors = Column(JSON)
    suggestions = Column(JSON)
    proposed_commands = Column(JSON)
    basis = Column(JSON)
    created_at = Column(BigInteger, default=current_milli_time)


class Alarm(Base):
    __tablename__ = "alarms"
    alarm_id = Column(String(26), primary_key=True)
    device_id = Column(String(64), ForeignKey("devices.device_id"), index=True)
    severity = Column(String(16))  # info, warning, critical
    source = Column(String(32))
    code = Column(String(64))
    title = Column(String(128))
    detail = Column(String(512))
    state = Column(String(16))  # open, acknowledged, resolved
    opened_at = Column(BigInteger, default=current_milli_time)
    acknowledged_at = Column(BigInteger, nullable=True)
    resolved_at = Column(BigInteger, nullable=True)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    kb_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128))
    description = Column(String(512))


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"
    item_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kb_id = Column(String(36), ForeignKey("knowledge_bases.kb_id"))
    title = Column(String(128))
    content = Column(String(2048))


class DiseasePhoto(Base):
    __tablename__ = "disease_photos"
    photo_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(64), ForeignKey("devices.device_id"), index=True)
    url = Column(String(255))
    original_name = Column(String(255))
    mime_type = Column(String(64))
    size_bytes = Column(Integer)
    analysis = Column(JSON, nullable=True)
    created_at = Column(BigInteger, default=current_milli_time)