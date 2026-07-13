from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from device_models import TelemetryRecord
from device_schemas import (
    AlarmRecordResponse,
    AlarmSettingsResponse,
    AlarmTargetRanges,
    DeviceHealthResponse,
    TelemetryInPayload,
)
from monitoring_models import AlarmRecord, AlarmRuleState, DeviceAlarmSetting, DevicePresence, TelemetryReceipt


DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "local_demo")
DEFAULT_DEVICE_NAME = os.getenv("DEFAULT_DEVICE_NAME", "一号大棚设备")
OFFLINE_AFTER_SECONDS = max(10, int(os.getenv("DEVICE_OFFLINE_SECONDS", "120")))
ALARM_SAMPLE_COUNT = 3

DEFAULT_ALARM_RANGES = {
    "temperature": {"min": 24.0, "max": 30.0},
    "humidity": {"min": 55.0, "max": 72.0},
    "light": {"min": 14000.0, "max": 24000.0},
    "co2": {"min": 520.0, "max": 900.0},
    "soil_moisture": {"min": 48.0, "max": 66.0},
    "soil_ec": {"min": 1.2, "max": 2.6},
    "gas_resistance": {"min": 12000.0, "max": 22000.0},
}

METRIC_DETAILS = {
    "temperature": ("棚内温度", "摄氏度"),
    "humidity": ("环境湿度", "%RH"),
    "light": ("光照强度", "lux"),
    "co2": ("二氧化碳浓度", "ppm"),
    "soil_moisture": ("土壤湿度", "%"),
    "soil_ec": ("土壤肥力", "mS/cm"),
    "gas_resistance": ("空气质量", "Ω"),
}


def now_ms() -> int:
    return int(time.time() * 1000)


def format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def range_dict(ranges: AlarmTargetRanges) -> dict:
    return ranges.model_dump()


def validated_ranges(value: object) -> AlarmTargetRanges:
    try:
        return AlarmTargetRanges.model_validate(value)
    except Exception:
        return AlarmTargetRanges.model_validate(DEFAULT_ALARM_RANGES)


def setting_for(db: Session, device_id: str, user_id: str = DEFAULT_USER_ID) -> Optional[DeviceAlarmSetting]:
    return (
        db.query(DeviceAlarmSetting)
        .filter(DeviceAlarmSetting.user_id == user_id, DeviceAlarmSetting.device_id == device_id)
        .first()
    )


def get_alarm_settings(db: Session, device_id: str, user_id: str = DEFAULT_USER_ID) -> AlarmSettingsResponse:
    setting = setting_for(db, device_id, user_id)
    if setting is None:
        return AlarmSettingsResponse(
            device_id=device_id,
            configured=False,
            ranges=validated_ranges(DEFAULT_ALARM_RANGES),
        )
    return AlarmSettingsResponse(
        device_id=device_id,
        configured=True,
        ranges=validated_ranges(setting.ranges),
        updated_at=setting.updated_at.strftime("%Y-%m-%d %H:%M") if setting.updated_at else None,
    )


def metric_values(record: TelemetryRecord) -> dict[str, float]:
    return {
        "temperature": record.temperature,
        "humidity": record.humidity,
        "light": record.light,
        "co2": record.co2,
        "soil_moisture": record.soil_moisture,
        "soil_ec": record.soil_ec,
        "gas_resistance": record.gas_resistance,
    }


def direction_for(value: float, minimum: float, maximum: float) -> Optional[str]:
    if value < minimum:
        return "low"
    if value > maximum:
        return "high"
    return None


def metric_advice(metric_key: str, direction: str) -> str:
    advice = {
        ("temperature", "high"): "建议检查通风和遮阳设备。",
        ("temperature", "low"): "建议检查保温措施和补光运行情况。",
        ("humidity", "high"): "建议加强通风并注意叶面结露。",
        ("humidity", "low"): "建议检查补水和空气加湿情况。",
        ("light", "high"): "建议适当遮阳并检查补光灯是否需要关闭。",
        ("light", "low"): "建议打开卷帘，必要时开启补光。",
        ("co2", "high"): "建议加强通风换气。",
        ("co2", "low"): "建议检查通风节奏并评估是否需要补充气肥。",
        ("soil_moisture", "high"): "建议暂停灌溉并检查排水情况。",
        ("soil_moisture", "low"): "建议检查供水并适量灌溉。",
        ("soil_ec", "high"): "建议检查施肥浓度并评估是否需要冲洗基质。",
        ("soil_ec", "low"): "建议检查养分供应和施肥计划。",
        ("gas_resistance", "high"): "建议结合其他环境指标继续观察。",
        ("gas_resistance", "low"): "建议检查通风状况和空气质量传感器。",
    }
    return advice.get((metric_key, direction), "建议检查相关环境调节设备。")


def alarm_text(metric_key: str, direction: str, value: float, minimum: float, maximum: float) -> tuple[str, str]:
    label, unit = METRIC_DETAILS[metric_key]
    direction_text = "高于" if direction == "high" else "低于"
    state_text = "偏高" if direction == "high" else "偏低"
    title = f"{label}{direction_text}目标范围"
    detail = (
        f"当前 {format_number(value)} {unit}，目标范围为 {format_number(minimum)} 至 "
        f"{format_number(maximum)} {unit}，已连续 {ALARM_SAMPLE_COUNT} 次{state_text}。"
        f"{metric_advice(metric_key, direction)}"
    )
    return title, detail


def alarm_to_response(alarm: AlarmRecord) -> AlarmRecordResponse:
    return AlarmRecordResponse(
        id=alarm.id,
        device_id=alarm.device_id,
        level=alarm.level,
        title=alarm.title,
        detail=alarm.detail,
        source=alarm.source,
        timestamp=alarm.opened_at,
        state=alarm.state,
        handled=alarm.state != "open",
        handled_at=alarm.handled_at,
        resolved_at=alarm.resolved_at,
    )


def rule_state_for(db: Session, device_id: str, rule_key: str, user_id: str) -> AlarmRuleState:
    state = (
        db.query(AlarmRuleState)
        .filter(
            AlarmRuleState.user_id == user_id,
            AlarmRuleState.device_id == device_id,
            AlarmRuleState.rule_key == rule_key,
        )
        .first()
    )
    if state is None:
        state = AlarmRuleState(
            user_id=user_id,
            device_id=device_id,
            rule_key=rule_key,
            direction=None,
            abnormal_count=0,
            normal_count=0,
            updated_at=now_ms(),
        )
        db.add(state)
        db.flush()
    return state


def current_alarm(db: Session, state: AlarmRuleState) -> Optional[AlarmRecord]:
    if not state.current_alarm_id:
        return None
    alarm = db.get(AlarmRecord, state.current_alarm_id)
    if alarm is None or alarm.state == "resolved":
        state.current_alarm_id = None
        return None
    return alarm


def resolve_alarm(alarm: AlarmRecord, timestamp: int, reason: Optional[str] = None) -> None:
    alarm.state = "resolved"
    alarm.resolved_at = timestamp
    alarm.updated_at = timestamp
    if reason:
        alarm.detail = f"{alarm.detail} {reason}".strip()


def evaluate_environment_alarms(
    db: Session,
    record: TelemetryRecord,
    user_id: str = DEFAULT_USER_ID,
) -> None:
    ranges = get_alarm_settings(db, record.device_id, user_id).ranges
    values = metric_values(record)
    timestamp = now_ms()

    for metric_key, value in values.items():
        target = getattr(ranges, metric_key)
        direction = direction_for(value, target.min, target.max)
        state = rule_state_for(db, record.device_id, f"metric:{metric_key}", user_id)
        alarm = current_alarm(db, state)

        if direction is None:
            state.abnormal_count = 0
            state.normal_count += 1
            state.updated_at = timestamp
            if alarm is not None and state.normal_count >= ALARM_SAMPLE_COUNT:
                resolve_alarm(alarm, timestamp, "该指标已连续 3 次回到目标范围。")
                state.current_alarm_id = None
                state.direction = None
                state.normal_count = 0
            continue

        state.normal_count = 0
        if state.direction != direction:
            state.direction = direction
            state.abnormal_count = 1
        else:
            state.abnormal_count += 1
        state.updated_at = timestamp

        if state.abnormal_count < ALARM_SAMPLE_COUNT:
            continue

        title, detail = alarm_text(metric_key, direction, value, target.min, target.max)
        if alarm is not None and alarm.direction != direction:
            resolve_alarm(alarm, timestamp, "指标越界方向已经改变。")
            state.current_alarm_id = None
            alarm = None

        if alarm is None:
            alarm = AlarmRecord(
                id=str(uuid.uuid4()),
                user_id=user_id,
                device_id=record.device_id,
                rule_key=f"metric:{metric_key}",
                metric_key=metric_key,
                direction=direction,
                level="warning",
                title=title,
                detail=detail,
                source="大棚环境监测",
                state="open",
                opened_at=timestamp,
                updated_at=timestamp,
            )
            db.add(alarm)
            state.current_alarm_id = alarm.id
        else:
            alarm.title = title
            alarm.detail = detail
            alarm.updated_at = timestamp


def apply_alarm_settings(
    db: Session,
    device_id: str,
    ranges: AlarmTargetRanges,
    user_id: str = DEFAULT_USER_ID,
) -> AlarmSettingsResponse:
    setting = setting_for(db, device_id, user_id)
    if setting is None:
        setting = DeviceAlarmSetting(user_id=user_id, device_id=device_id, ranges=range_dict(ranges))
        db.add(setting)
    else:
        setting.ranges = range_dict(ranges)
        setting.updated_at = datetime.utcnow()
    db.flush()

    latest = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.device_id == device_id)
        .order_by(desc(TelemetryRecord.timestamp), desc(TelemetryRecord.id))
        .first()
    )
    values = metric_values(latest) if latest is not None else {}
    timestamp = now_ms()
    states = (
        db.query(AlarmRuleState)
        .filter(AlarmRuleState.user_id == user_id, AlarmRuleState.device_id == device_id)
        .all()
    )
    for state in states:
        state.abnormal_count = 0
        state.normal_count = 0
        state.updated_at = timestamp
        alarm = current_alarm(db, state)
        if not state.rule_key.startswith("metric:"):
            continue
        metric_key = state.rule_key.split(":", 1)[1]
        if metric_key not in values:
            continue
        target = getattr(ranges, metric_key)
        direction = direction_for(values[metric_key], target.min, target.max)
        state.direction = direction
        if alarm is not None and direction is None:
            resolve_alarm(alarm, timestamp, "目标范围调整后，该指标已处于正常范围。")
            state.current_alarm_id = None
        elif alarm is not None and direction is not None:
            alarm.direction = direction
            alarm.title, alarm.detail = alarm_text(
                metric_key,
                direction,
                values[metric_key],
                target.min,
                target.max,
            )
            alarm.updated_at = timestamp

    db.commit()
    db.refresh(setting)
    return get_alarm_settings(db, device_id, user_id)


def list_alarms(
    db: Session,
    device_id: str,
    limit: int,
    state_filter: Optional[str] = None,
    user_id: str = DEFAULT_USER_ID,
) -> list[AlarmRecordResponse]:
    query = db.query(AlarmRecord).filter(
        AlarmRecord.user_id == user_id,
        AlarmRecord.device_id == device_id,
    )
    if state_filter:
        query = query.filter(AlarmRecord.state == state_filter)
    alarms = query.order_by(desc(AlarmRecord.opened_at)).limit(limit).all()
    return [alarm_to_response(alarm) for alarm in alarms]


def acknowledge_alarm(db: Session, alarm_id: str, user_id: str = DEFAULT_USER_ID) -> AlarmRecordResponse:
    alarm = db.query(AlarmRecord).filter(AlarmRecord.id == alarm_id, AlarmRecord.user_id == user_id).first()
    if alarm is None:
        raise LookupError("报警记录不存在")
    if alarm.state == "open":
        alarm.state = "acknowledged"
        alarm.handled_at = now_ms()
        alarm.updated_at = alarm.handled_at
        db.commit()
        db.refresh(alarm)
    return alarm_to_response(alarm)


def find_duplicate_record(db: Session, device_id: str, message_id: Optional[str]) -> Optional[TelemetryRecord]:
    if not message_id:
        return None
    receipt = (
        db.query(TelemetryReceipt)
        .filter(TelemetryReceipt.device_id == device_id, TelemetryReceipt.message_id == message_id)
        .first()
    )
    return db.get(TelemetryRecord, receipt.telemetry_record_id) if receipt is not None else None


def add_telemetry_receipt(
    db: Session,
    record: TelemetryRecord,
    payload: TelemetryInPayload,
    transport: str,
) -> None:
    receipt = (
        db.query(TelemetryReceipt)
        .filter(TelemetryReceipt.telemetry_record_id == record.id)
        .first()
    )
    if receipt is None:
        receipt = TelemetryReceipt(
            telemetry_record_id=record.id,
            device_id=record.device_id,
            message_id=payload.message_id,
            sequence=payload.sequence,
            transport=transport,
            normalized_payload=payload.model_dump(mode="json"),
            received_at=record.received_at,
        )
        db.add(receipt)
        return
    receipt.device_id = record.device_id
    receipt.message_id = payload.message_id
    receipt.sequence = payload.sequence
    receipt.transport = transport
    receipt.normalized_payload = payload.model_dump(mode="json")
    receipt.received_at = record.received_at


def active_rule_alarm(db: Session, device_id: str, rule_key: str, user_id: str) -> Optional[AlarmRecord]:
    return (
        db.query(AlarmRecord)
        .filter(
            AlarmRecord.user_id == user_id,
            AlarmRecord.device_id == device_id,
            AlarmRecord.rule_key == rule_key,
            AlarmRecord.state != "resolved",
        )
        .order_by(desc(AlarmRecord.opened_at))
        .first()
    )


def mark_device_seen(
    db: Session,
    device_id: str,
    transport: str,
    telemetry_at: Optional[int] = None,
    user_id: str = DEFAULT_USER_ID,
) -> DevicePresence:
    timestamp = now_ms()
    presence = db.get(DevicePresence, device_id)
    if presence is None:
        presence = DevicePresence(
            device_id=device_id,
            online=True,
            transport=transport,
            last_seen_at=timestamp,
            last_telemetry_at=telemetry_at or timestamp,
        )
        db.add(presence)
    else:
        presence.online = True
        presence.transport = transport
        presence.last_seen_at = timestamp
        if telemetry_at is not None:
            presence.last_telemetry_at = telemetry_at

    alarm = active_rule_alarm(db, device_id, "device_offline", user_id)
    if alarm is not None:
        resolve_alarm(alarm, timestamp, "设备已经恢复数据上报。")
    return presence


def mark_device_offline(db: Session, presence: DevicePresence, user_id: str = DEFAULT_USER_ID) -> None:
    if not presence.online:
        return
    timestamp = now_ms()
    presence.online = False
    alarm = active_rule_alarm(db, presence.device_id, "device_offline", user_id)
    if alarm is None:
        alarm = AlarmRecord(
            id=str(uuid.uuid4()),
            user_id=user_id,
            device_id=presence.device_id,
            rule_key="device_offline",
            metric_key=None,
            direction=None,
            level="danger",
            title="大棚设备已离线",
            detail="较长时间没有收到设备数据，请检查设备供电和网络连接。",
            source="设备连接状态",
            state="open",
            opened_at=timestamp,
            updated_at=timestamp,
        )
        db.add(alarm)


def update_device_connection_status(
    db: Session,
    device_id: str,
    online: bool,
    transport: str = "mqtt",
) -> None:
    if online:
        mark_device_seen(db, device_id, transport)
    else:
        presence = db.get(DevicePresence, device_id)
        if presence is not None:
            mark_device_offline(db, presence)
    db.commit()


def check_offline_devices(db: Session, current_time_ms: Optional[int] = None) -> int:
    timestamp = current_time_ms if current_time_ms is not None else now_ms()
    cutoff = timestamp - OFFLINE_AFTER_SECONDS * 1000
    presences = db.query(DevicePresence).filter(DevicePresence.online.is_(True), DevicePresence.last_seen_at < cutoff).all()
    for presence in presences:
        mark_device_offline(db, presence)
    if presences:
        db.commit()
    return len(presences)


def get_device_health(db: Session, device_id: str) -> DeviceHealthResponse:
    presence = db.get(DevicePresence, device_id)
    if presence is None:
        latest = (
            db.query(TelemetryRecord)
            .filter(TelemetryRecord.device_id == device_id)
            .order_by(desc(TelemetryRecord.timestamp), desc(TelemetryRecord.id))
            .first()
        )
        if latest is None:
            raise LookupError("暂时没有收到该设备的数据")
        presence = DevicePresence(
            device_id=device_id,
            online=True,
            transport="http",
            last_seen_at=latest.received_at,
            last_telemetry_at=latest.received_at,
        )
        db.add(presence)
        db.flush()

    if presence.online and presence.last_seen_at < now_ms() - OFFLINE_AFTER_SECONDS * 1000:
        mark_device_offline(db, presence)
    db.commit()
    db.refresh(presence)
    return DeviceHealthResponse(
        device_id=device_id,
        device_name=DEFAULT_DEVICE_NAME,
        online=presence.online,
        transport="mqtt" if presence.transport == "mqtt" else "http",
        last_seen_at=presence.last_seen_at,
        last_telemetry_at=presence.last_telemetry_at,
        offline_after_seconds=OFFLINE_AFTER_SECONDS,
    )
