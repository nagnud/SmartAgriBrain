from __future__ import annotations

import logging
import os
import re
import time
import uuid
from typing import Any, Callable

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from device_schemas import DeviceCommandRequest
from device_service import queue_command
from monitoring_service import get_alarm_settings
from position_service import take_position_result
from schemas import AssistantTurnRequest
from site_events import site_event_bus
from water_gun_service import WaterGunPreviewRequest, WaterGunStaticRequest, water_gun_runtime
from site_models import (
    EdgeAssistantAction,
    EdgeAssistantMessage,
    EdgeAssistantSession,
    EdgeDeviceRecord,
    SiteCommandRecord,
    SiteHistorySample,
    SiteSnapshotRecord,
)
from site_schemas import (
    ActuatorState,
    EdgeAssistantActionResponse,
    EdgeAssistantConversationResponse,
    EdgeAssistantMessageResponse,
    EdgeDeviceState,
    SiteCommandRequest,
    SiteCommandResponse,
    SiteHistoryPoint,
    SiteState,
)


logger = logging.getLogger(__name__)


SENSOR_KEYS = (
    "temperature_c",
    "humidity_pct",
    "pressure_kpa",
    "gas_resistance_ohm",
    "illuminance_lux",
    "co2_ppm",
    "soil_moisture_pct",
    "soil_ec_ms_cm",
)
# These are the only physical actuator states exposed by the current ESP32.
# The pump is water-gun internal state, not a generic command target. Water-gun
# positioning and spray operations use their separate target_position contract.
ACTUATOR_KEYS = ("grow_light",)
DEVICE_OFFLINE_AFTER_MS = 30_000
COMMAND_TTL_MS = 30_000
HISTORY_SAMPLE_INTERVAL_MS = 10_000
HISTORY_RETENTION_MS = 24 * 60 * 60 * 1000
VISIBLE_HISTORY_SENSOR_KEYS = (
    "temperature_c",
    "illuminance_lux",
    "co2_ppm",
    "soil_moisture_pct",
)
DISPLAY_SENSOR_RANGES = {
    "temperature_c": "temperature",
    "humidity_pct": "humidity",
    "illuminance_lux": "light",
    "co2_ppm": "co2",
}


def now_ms() -> int:
    return int(time.time() * 1000)


def default_site_id() -> str:
    return os.getenv("DEFAULT_SITE_ID", "greenhouse_001").strip() or "greenhouse_001"


def s3_device_id() -> str:
    return os.getenv("S3_DEVICE_ID", "greenhouse_001_s3").strip() or "greenhouse_001_s3"


def c5_device_id() -> str:
    return os.getenv("C5_DEVICE_ID", "greenhouse_001_c5").strip() or "greenhouse_001_c5"


def _float_or_none(value: Any, minimum: float | None = None, maximum: float | None = None) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    if minimum is not None and number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def _actuator_state(raw: Any, *, supported_default: bool = False) -> dict[str, Any]:
    if isinstance(raw, dict):
        supported = bool(raw.get("supported", supported_default))
        desired = _float_or_none(raw.get("desired"), 0, 100)
        actual = _float_or_none(raw.get("actual"), 0, 100)
        master_raw = raw.get("master_enabled")
        master_enabled = master_raw if isinstance(master_raw, bool) else None
    else:
        supported = raw is not None or supported_default
        desired = actual = _float_or_none(raw, 0, 100)
        master_enabled = actual > 0 if actual is not None else None
    return {
        "supported": supported,
        "desired": round(desired) if desired is not None else None,
        "actual": round(actual) if actual is not None else None,
        "unit": "percent",
        "master_enabled": master_enabled,
    }


def normalize_site_telemetry(raw: dict[str, Any], topic_device_id: str | None = None) -> dict[str, Any]:
    device_id = str(raw.get("device_id") or topic_device_id or "").strip()
    if not device_id or (topic_device_id and device_id != topic_device_id):
        raise ValueError("device_id does not match MQTT topic")
    site_id = str(raw.get("site_id") or default_site_id()).strip()
    message_id = str(raw.get("message_id") or "").strip()
    try:
        uuid.UUID(message_id)
    except (ValueError, AttributeError):
        raise ValueError("message_id must be a UUID") from None
    sampled_at = int(raw.get("sampled_at") or raw.get("timestamp") or now_ms())
    if sampled_at < 1_000_000_000_000:
        sampled_at = now_ms()

    sensor_input = raw.get("sensors") if isinstance(raw.get("sensors"), dict) else {}
    sensor_aliases = {
        "temperature_c": "temperature",
        "humidity_pct": "humidity",
        "pressure_kpa": "pressure",
        "gas_resistance_ohm": "gas_resistance",
        "illuminance_lux": "light",
        "co2_ppm": "co2",
        "soil_moisture_pct": "soil_moisture",
        "soil_ec_ms_cm": "soil_ec",
    }
    ranges = {
        "temperature_c": (-80, 100),
        "humidity_pct": (0, 100),
        "pressure_kpa": (0, 2000),
        "gas_resistance_ohm": (0, None),
        "illuminance_lux": (0, None),
        "co2_ppm": (0, None),
        "soil_moisture_pct": (0, 100),
        "soil_ec_ms_cm": (0, None),
    }
    sensors: dict[str, float | None] = {}
    for key in SENSOR_KEYS:
        raw_value = sensor_input.get(key, sensor_input.get(sensor_aliases[key]))
        minimum, maximum = ranges[key]
        sensors[key] = _float_or_none(raw_value, minimum, maximum)

    raw_quality = raw.get("quality") if isinstance(raw.get("quality"), dict) else {}
    quality = {
        key: str(raw_quality.get(key) or ("ok" if sensors[key] is not None else "unsupported"))
        for key in SENSOR_KEYS
    }
    actuator_input = raw.get("actuators") if isinstance(raw.get("actuators"), dict) else {}
    actuators = {
        key: _actuator_state(actuator_input.get(key), supported_default=key == "grow_light")
        for key in ACTUATOR_KEYS
    }
    connectivity = raw.get("connectivity") if isinstance(raw.get("connectivity"), dict) else {}
    return {
        "schema_version": "1.0",
        "site_id": site_id,
        "device_id": device_id,
        "message_id": message_id,
        "sampled_at": sampled_at,
        "sequence": raw.get("sequence"),
        "sensors": sensors,
        "quality": quality,
        "actuators": actuators,
        "connectivity": connectivity,
    }


def _upsert_device(
    db: Session,
    device_id: str,
    site_id: str,
    role: str,
    *,
    online: bool | None = None,
    status: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None,
) -> EdgeDeviceRecord:
    record = db.get(EdgeDeviceRecord, device_id)
    if record is None:
        record = EdgeDeviceRecord(device_id=device_id, site_id=site_id, role=role, online=False, last_seen_at=0)
        db.add(record)
    record.site_id = site_id
    record.role = role
    record.last_seen_at = now_ms()
    if online is not None:
        record.online = online
    if status is not None:
        record.status = status
    if capabilities is not None:
        record.capabilities = capabilities
    return record


def _history_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    sensors = payload.get("sensors")
    if not isinstance(sensors, dict):
        return None
    if all(sensors.get(key) is None for key in VISIBLE_HISTORY_SENSOR_KEYS):
        return None
    return {
        "sensors": dict(sensors),
        "quality": dict(payload.get("quality") or {}),
    }


def _upsert_history_sample(db: Session, payload: dict[str, Any], received_at: int) -> None:
    history_payload = _history_payload(payload)
    if history_payload is None:
        return
    sampled_at = int(payload["sampled_at"])
    bucket_at = sampled_at // HISTORY_SAMPLE_INTERVAL_MS * HISTORY_SAMPLE_INTERVAL_MS
    sample = db.scalar(
        select(SiteHistorySample).where(
            SiteHistorySample.site_id == payload["site_id"],
            SiteHistorySample.bucket_at == bucket_at,
        )
    )
    if sample is None:
        db.add(
            SiteHistorySample(
                site_id=payload["site_id"],
                device_id=payload["device_id"],
                bucket_at=bucket_at,
                sampled_at=sampled_at,
                received_at=received_at,
                payload=history_payload,
            )
        )
        return
    # Each ten-second bucket keeps the newest real reading; no values are interpolated.
    if sampled_at >= sample.sampled_at:
        sample.device_id = payload["device_id"]
        sample.sampled_at = sampled_at
        sample.received_at = received_at
        sample.payload = history_payload


def _prune_site_history(db: Session, current_time_ms: int) -> None:
    cutoff = current_time_ms - HISTORY_RETENTION_MS
    db.execute(delete(SiteHistorySample).where(SiteHistorySample.sampled_at < cutoff))


def _backfill_site_history_from_snapshots(db: Session, site_id: str) -> None:
    existing_sample_id = db.scalar(
        select(SiteHistorySample.id).where(SiteHistorySample.site_id == site_id).limit(1)
    )
    if existing_sample_id is not None:
        return

    current_time_ms = now_ms()
    cutoff = current_time_ms - HISTORY_RETENTION_MS
    snapshots = db.scalars(
        select(SiteSnapshotRecord)
        .where(SiteSnapshotRecord.site_id == site_id, SiteSnapshotRecord.sampled_at >= cutoff)
        .order_by(SiteSnapshotRecord.sampled_at.asc(), SiteSnapshotRecord.id.asc())
    ).all()
    if not snapshots:
        return

    for snapshot in snapshots:
        if isinstance(snapshot.payload, dict):
            _upsert_history_sample(db, snapshot.payload, snapshot.received_at)
    db.flush()
    _prune_site_history(db, current_time_ms)
    db.commit()


def save_site_telemetry(db: Session, raw: dict[str, Any], topic_device_id: str | None = None) -> SiteState:
    payload = normalize_site_telemetry(raw, topic_device_id)
    received_at = now_ms()
    existing = db.scalar(select(SiteSnapshotRecord).where(SiteSnapshotRecord.message_id == payload["message_id"]))
    if existing is None:
        db.add(
            SiteSnapshotRecord(
                site_id=payload["site_id"],
                device_id=payload["device_id"],
                message_id=payload["message_id"],
                sampled_at=payload["sampled_at"],
                received_at=received_at,
                payload=payload,
            )
        )
    _upsert_history_sample(db, payload, received_at)
    # Flush first so a stale reading received now is also covered by retention.
    db.flush()
    _prune_site_history(db, received_at)
    _upsert_device(
        db,
        payload["device_id"],
        payload["site_id"],
        "sensor_actuator",
        online=True,
        status=payload.get("connectivity", {}),
    )
    db.commit()
    state = get_site_state(db, payload["site_id"])
    site_event_bus.publish(payload["site_id"], "telemetry", state.model_dump(mode="json"))
    return state


def _site_history_point_from_payload(timestamp: int, payload: dict[str, Any]) -> SiteHistoryPoint | None:
    if _history_payload(payload) is None:
        return None
    sensors = payload.get("sensors")
    if not isinstance(sensors, dict):
        return None
    try:
        return SiteHistoryPoint(
            timestamp=timestamp,
            temperature=_float_or_none(sensors.get("temperature_c"), -80, 100),
            light=_float_or_none(sensors.get("illuminance_lux"), 0),
            co2=_float_or_none(sensors.get("co2_ppm"), 0),
            soil_moisture=_float_or_none(sensors.get("soil_moisture_pct"), 0, 100),
            humidity=_float_or_none(sensors.get("humidity_pct"), 0, 100),
            gas_resistance=_float_or_none(sensors.get("gas_resistance_ohm"), 0),
            soil_ec=_float_or_none(sensors.get("soil_ec_ms_cm"), 0),
        )
    except (KeyError, TypeError, ValueError):
        return None


def get_site_history(db: Session, site_id: str, hours: int = 6) -> list[SiteHistoryPoint]:
    _backfill_site_history_from_snapshots(db, site_id)
    bounded_hours = min(max(hours, 1), 24)
    cutoff = now_ms() - bounded_hours * 60 * 60 * 1000
    snapshots = db.scalars(
        select(SiteSnapshotRecord)
        .where(SiteSnapshotRecord.site_id == site_id, SiteSnapshotRecord.sampled_at >= cutoff)
        .order_by(SiteSnapshotRecord.sampled_at.asc(), SiteSnapshotRecord.id.asc())
    ).all()
    points: list[SiteHistoryPoint] = []
    for snapshot in snapshots:
        if not isinstance(snapshot.payload, dict):
            continue
        point = _site_history_point_from_payload(snapshot.sampled_at, snapshot.payload)
        if point is not None:
            points.append(point)
    return points


def update_edge_status(db: Session, raw: dict[str, Any], topic_device_id: str) -> SiteState:
    device_id = str(raw.get("device_id") or topic_device_id)
    if device_id != topic_device_id:
        raise ValueError("device_id does not match MQTT topic")
    site_id = str(raw.get("site_id") or default_site_id())
    role = "voice_display" if device_id == c5_device_id() else "sensor_actuator"
    online_value = raw.get("online")
    online = online_value if isinstance(online_value, bool) else str(online_value).lower() in {"1", "true", "online"}
    _upsert_device(db, device_id, site_id, role, online=online, status=raw)
    db.commit()
    state = get_site_state(db, site_id)
    site_event_bus.publish(site_id, "device_status", state.model_dump(mode="json"))
    return state


def update_edge_capabilities(db: Session, raw: dict[str, Any], topic_device_id: str) -> SiteState:
    device_id = str(raw.get("device_id") or topic_device_id)
    if device_id != topic_device_id:
        raise ValueError("device_id does not match MQTT topic")
    site_id = str(raw.get("site_id") or default_site_id())
    role = "voice_display" if device_id == c5_device_id() else "sensor_actuator"
    _upsert_device(db, device_id, site_id, role, online=True, capabilities=raw)
    db.commit()
    state = get_site_state(db, site_id)
    site_event_bus.publish(site_id, "capabilities", state.model_dump(mode="json"))
    return state


def get_site_state(db: Session, site_id: str) -> SiteState:
    snapshot = db.scalar(
        select(SiteSnapshotRecord)
        .where(SiteSnapshotRecord.site_id == site_id)
        .order_by(SiteSnapshotRecord.sampled_at.desc(), SiteSnapshotRecord.id.desc())
        .limit(1)
    )
    if snapshot is None:
        sensors = {key: None for key in SENSOR_KEYS}
        quality = {key: "unavailable" for key in SENSOR_KEYS}
        actuators = {
            key: ActuatorState(supported=key == "grow_light") for key in ACTUATOR_KEYS
        }
        updated_at = 0
    else:
        sensors = snapshot.payload.get("sensors", {})
        quality = snapshot.payload.get("quality", {})
        actuators = {
            key: ActuatorState.model_validate(snapshot.payload.get("actuators", {}).get(key, {}))
            for key in ACTUATOR_KEYS
        }
        updated_at = snapshot.sampled_at
    device_rows = db.scalars(select(EdgeDeviceRecord).where(EdgeDeviceRecord.site_id == site_id)).all()
    observed_at = now_ms()
    devices = {
        row.device_id: EdgeDeviceState(
            device_id=row.device_id,
            role=row.role,
            online=row.online and row.last_seen_at >= observed_at - DEVICE_OFFLINE_AFTER_MS,
            last_seen_at=row.last_seen_at,
            status=row.status or {},
            capabilities=row.capabilities or {},
        )
        for row in device_rows
    }
    target_ranges = get_alarm_settings(db, s3_device_id()).ranges.model_dump()
    sensor_display: dict[str, str] = {}
    for sensor_key, range_key in DISPLAY_SENSOR_RANGES.items():
        value = sensors.get(sensor_key)
        sensor_quality = str(quality.get(sensor_key) or ("ok" if value is not None else "unavailable"))
        if value is None or sensor_quality != "ok":
            sensor_display[sensor_key] = "unavailable"
            continue
        target = target_ranges[range_key]
        if float(value) > float(target["max"]):
            sensor_display[sensor_key] = "high"
        elif float(value) < float(target["min"]):
            sensor_display[sensor_key] = "low"
        else:
            sensor_display[sensor_key] = "normal"
    return SiteState(
        site_id=site_id,
        updated_at=updated_at,
        sensors=sensors,
        quality=quality,
        sensor_display=sensor_display,
        actuators=actuators,
        devices=devices,
    )


def _command_response(record: SiteCommandRecord) -> SiteCommandResponse:
    return SiteCommandResponse(
        command_id=record.command_id,
        site_id=record.site_id,
        device_id=record.device_id,
        target=record.target,
        value=record.value,
        state=record.state,
        created_at=record.created_at,
        expires_at=record.expires_at,
        actual_value=record.actual_value,
        error=record.error,
        assistant_action_id=record.assistant_action_id,
    )


def queue_site_command(
    db: Session,
    site_id: str,
    request: SiteCommandRequest,
    *,
    assistant_action_id: str | None = None,
) -> SiteCommandResponse:
    created_at = now_ms()
    record = SiteCommandRecord(
        command_id=str(uuid.uuid4()),
        site_id=site_id,
        device_id=s3_device_id(),
        target=request.target,
        value=request.value,
        reason=request.reason,
        source=request.source,
        assistant_action_id=assistant_action_id,
        state="queued",
        created_at=created_at,
        expires_at=created_at + COMMAND_TTL_MS,
        acknowledged_at=None,
        actual_value=None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    response = _command_response(record)
    site_event_bus.publish(site_id, "command_update", response.model_dump(mode="json"))
    return response


def claim_next_site_command(db: Session) -> SiteCommandRecord | None:
    current = now_ms()
    db.execute(
        update(SiteCommandRecord)
        .where(SiteCommandRecord.state == "queued", SiteCommandRecord.expires_at < current)
        .values(state="expired", error={"code": "COMMAND_EXPIRED", "message": "command_expired"})
    )
    db.commit()
    record = db.scalar(
        select(SiteCommandRecord)
        .where(SiteCommandRecord.state == "queued", SiteCommandRecord.expires_at >= current)
        .order_by(SiteCommandRecord.created_at.asc())
        .limit(1)
    )
    if record is None:
        return None
    record.state = "dispatched"
    record.dispatched_at = current
    db.commit()
    db.refresh(record)
    site_event_bus.publish(record.site_id, "command_update", _command_response(record).model_dump(mode="json"))
    return record


def expire_site_commands(db: Session) -> int:
    current = now_ms()
    records = db.scalars(
        select(SiteCommandRecord).where(
            SiteCommandRecord.state.in_(("queued", "dispatched")),
            SiteCommandRecord.expires_at < current,
        )
    ).all()
    for record in records:
        record.state = "expired"
        record.error = {"code": "COMMAND_EXPIRED", "message": "command_expired"}
    if not records:
        return 0
    db.commit()
    for record in records:
        site_event_bus.publish(record.site_id, "command_update", _command_response(record).model_dump(mode="json"))
    return len(records)


def return_site_command_to_queue(db: Session, command_id: str) -> None:
    record = db.scalar(select(SiteCommandRecord).where(SiteCommandRecord.command_id == command_id))
    if record is not None and record.state == "dispatched" and record.expires_at >= now_ms():
        record.state = "queued"
        record.dispatched_at = None
        db.commit()


def acknowledge_site_command(db: Session, raw: dict[str, Any]) -> SiteCommandResponse:
    command_id = str(raw.get("command_id") or "")
    record = db.scalar(select(SiteCommandRecord).where(SiteCommandRecord.command_id == command_id))
    if record is None:
        raise LookupError("unknown command_id")
    if record.state in {"succeeded", "failed", "expired"}:
        return _command_response(record)
    succeeded = str(raw.get("state") or "").lower() in {"executed", "succeeded", "success"}
    record.state = "succeeded" if succeeded else "failed"
    record.acknowledged_at = int(raw.get("acknowledged_at") or now_ms())
    record.actual_value = int(raw.get("actual_value")) if succeeded and raw.get("actual_value") is not None else None
    record.error = raw.get("error") if isinstance(raw.get("error"), dict) else None
    if record.assistant_action_id:
        action = db.get(EdgeAssistantAction, record.assistant_action_id)
        if action is not None:
            action.state = "executed" if succeeded else "failed"
            action.resolved_at = now_ms()
    db.commit()
    response = _command_response(record)
    if record.source == "edge_voice":
        logger.info(
            "C5 assistant stage=ack command_id=%s target=%s state=%s actual_value=%s",
            record.command_id,
            record.target,
            record.state,
            record.actual_value,
        )
    site_event_bus.publish(record.site_id, "command_update", response.model_dump(mode="json"))
    return response


def command_wire_payload(record: SiteCommandRecord) -> dict[str, Any]:
    """Build the compact MQTT command consumed by the ESP32.

    The Topic already carries protocol version and device identity. The
    database keeps site, source, reason, and creation time for audit, so those
    fields do not need to be repeated over the device link.
    """
    return {
        "command_id": record.command_id,
        "expires_at": record.expires_at,
        "command": {"operation": "set", "target": record.target, "value": record.value},
    }


def _brief_text(text: str) -> str:
    cleaned = re.sub(r"[`#*_>]", "", text).strip()
    sentences = re.split(r"(?<=[。！？!?])\s*", cleaned)
    brief = "".join(sentences[:3]).strip() or cleaned
    return brief[:120]


def _ensure_session(db: Session, site_id: str, session_id: str | None, channel: str) -> EdgeAssistantSession:
    session = db.get(EdgeAssistantSession, session_id) if session_id else None
    current = now_ms()
    if session is None:
        session = EdgeAssistantSession(
            id=session_id or f"edge-{uuid.uuid4()}",
            site_id=site_id,
            channel=channel,
            created_at=current,
            updated_at=current,
        )
        db.add(session)
    elif session.site_id != site_id:
        raise ValueError("assistant session belongs to another site")
    session.updated_at = current
    return session


def _action_response(action: EdgeAssistantAction) -> EdgeAssistantActionResponse:
    return EdgeAssistantActionResponse(
        id=action.id,
        type=action.action_type,
        risk=action.risk,
        state=action.state,
        payload=action.payload,
        expires_at=action.expires_at,
    )


def _message_response(message: EdgeAssistantMessage, actions: list[EdgeAssistantAction]) -> EdgeAssistantMessageResponse:
    current = now_ms()
    next_input = "none"
    input_hint: str | None = None
    input_candidates: list[str] = []
    if any(action.state == "pending" and action.expires_at >= current for action in actions):
        next_input = "confirmation"
    elif isinstance(message.message_metadata, dict):
        context = message.message_metadata.get("assistant_context")
        if isinstance(context, dict) and not context.get("water_gun_duration_resolved"):
            duration_request = context.get("water_gun_duration_request")
            if (
                isinstance(duration_request, dict)
                and int(duration_request.get("expires_at") or 0) >= current
            ):
                next_input = "duration"
                input_hint = "water_gun_duration"
                input_candidates = ["10秒", "30秒", "1分钟", "持续喷水"]
        if isinstance(context, dict):
            manual_request = context.get("c5_manual_water_gun_request")
            if (
                next_input == "none"
                and isinstance(manual_request, dict)
                and int(manual_request.get("expires_at") or 0) >= current
            ):
                if manual_request.get("stage") == "direction":
                    next_input = "parameter"
                    input_hint = "manual_water_gun_direction"
                    # Optional protocol-v2 suggestions.  Legacy C5 keeps using
                    # the sentence prompt and can answer by voice as before.
                    input_candidates = ["左侧", "右侧", "不偏移"]
                elif manual_request.get("stage") == "duration":
                    next_input = "duration"
                    input_hint = "manual_water_gun_duration"
                    input_candidates = ["10秒", "30秒", "1分钟", "持续喷水"]
            parameter_request = context.get("c5_parameter_request")
            if (
                next_input == "none"
                and isinstance(parameter_request, dict)
                and int(parameter_request.get("expires_at") or 0) >= current
            ):
                next_input = "parameter"
                input_hint = str(parameter_request.get("kind") or "percentage_or_auto")
                candidates = parameter_request.get("candidates")
                if isinstance(candidates, list):
                    input_candidates = [str(item) for item in candidates[:6]]
    return EdgeAssistantMessageResponse(
        id=message.id,
        session_id=message.session_id,
        site_id=message.site_id,
        role=message.role,
        channel=message.channel,
        content=message.content,
        created_at=message.created_at,
        actions=[_action_response(action) for action in actions],
        next_input=next_input,
        input_hint=input_hint,
        input_candidates=input_candidates,
    )


def _assistant_water_gun_target(action: EdgeAssistantAction) -> tuple[float, float, str, str] | None:
    manual_target = action.payload.get("manual_target")
    if isinstance(manual_target, dict):
        try:
            ground_range_mm = float(manual_target["ground_range_mm"])
            bearing_deg = float(manual_target["bearing_deg"])
        except (KeyError, TypeError, ValueError):
            return None
        if not 0 <= ground_range_mm <= 1_000_000 or not -180 <= bearing_deg <= 180:
            return None
        return (
            ground_range_mm,
            bearing_deg,
            str(action.payload.get("target_label") or "手动目标")[:120],
            "manual",
        )
    result_id = str(action.payload.get("result_id") or "")
    stored_result = take_position_result(result_id)
    if stored_result is None:
        return None
    candidate, _captured_at = stored_result
    return candidate.ground_range_mm, candidate.bearing_deg, candidate.label, "vision"


def create_edge_assistant_reply(
    db: Session,
    site_id: str,
    text: str,
    session_id: str | None,
    channel: str,
    *,
    message_id: str | None = None,
    delta: Callable[[str], None] | None = None,
    event: Callable[[str, dict[str, Any]], None] | None = None,
) -> EdgeAssistantMessageResponse:
    # The edge display and web UI now share the same context-aware orchestrator,
    # while retaining separate session ids and channel-specific answer lengths.
    from assistant_orchestrator import run_assistant_turn

    resolved_session_id = session_id or f"edge-{uuid.uuid4()}"
    resolved_message_id = message_id or f"msg-{uuid.uuid4()}"
    if message_id:
        existing_messages = list(
            db.scalars(
                select(EdgeAssistantMessage)
                .where(
                    EdgeAssistantMessage.session_id == resolved_session_id,
                    EdgeAssistantMessage.role == "assistant",
                )
                .order_by(EdgeAssistantMessage.created_at.desc())
            ).all()
        )
        existing = next(
            (
                item
                for item in existing_messages
                if isinstance(item.message_metadata, dict)
                and item.message_metadata.get("reply_to_message_id") == resolved_message_id
            ),
            None,
        )
        if existing is not None:
            existing_actions = list(
                db.scalars(select(EdgeAssistantAction).where(EdgeAssistantAction.message_id == existing.id)).all()
            )
            return _message_response(existing, existing_actions)
    orchestrated = run_assistant_turn(
        AssistantTurnRequest(
            session_id=resolved_session_id,
            site_id=site_id,
            channel="edge_text" if channel == "edge_text" else "web",
            message_id=resolved_message_id,
            text=text,
        ),
        delta=delta,
        event=event,
    )
    db.expire_all()
    assistant_message = db.get(EdgeAssistantMessage, orchestrated.message.id)
    if assistant_message is None:
        raise RuntimeError("assistant response was not persisted")
    actions = list(
        db.scalars(
            select(EdgeAssistantAction)
            .where(EdgeAssistantAction.message_id == assistant_message.id)
            .order_by(EdgeAssistantAction.created_at.asc())
        ).all()
    )
    response = _message_response(assistant_message, actions)
    site_event_bus.publish(site_id, "assistant_message", response.model_dump(mode="json"))
    return response


def decide_edge_assistant_action(db: Session, site_id: str, action_id: str, decision: str) -> EdgeAssistantActionResponse:
    action = db.get(EdgeAssistantAction, action_id)
    if action is None or action.site_id != site_id:
        raise LookupError("assistant action not found")
    current = now_ms()
    if action.state != "pending":
        return _action_response(action)
    if action.expires_at < current:
        action.state = "expired"
        action.resolved_at = current
    elif decision == "cancel":
        if action.action_type == "water_gun_target":
            target = _assistant_water_gun_target(action)
            if target is not None:
                ground_range_mm, bearing_deg, target_label, source = target
                preview = water_gun_runtime.set_preview(
                    site_id,
                    WaterGunPreviewRequest(
                        ground_range_mm=ground_range_mm,
                        bearing_deg=bearing_deg,
                        device_id=s3_device_id(),
                        source=source,
                        target_label=target_label,
                        spray_enabled=False,
                    ),
                )
                action.payload = {**action.payload, "water_gun": preview.model_dump(mode="json")}
        action.state = "canceled"
        action.resolved_at = current
    elif action.action_type == "reply_choice":
        reply = str(action.payload.get("reply") or "").strip()
        if not reply:
            action.state = "failed"
        else:
            action.state = "executed"
            action.payload = {**action.payload, "selected_at": current}
        action.resolved_at = current
    elif action.action_type == "device_command":
        command = str(action.payload.get("command") or "")
        target_map = {"light": "grow_light"}
        payload_target = str(action.payload.get("target") or "")
        target = payload_target if payload_target in set(target_map.values()) else target_map.get(command.rsplit("_", 1)[0])
        if target is None:
            action.state = "failed"
            action.resolved_at = current
            action.payload = {
                **action.payload,
                "error": "The current ESP32 firmware does not declare this actuator.",
            }
        else:
            from c5_assistant_capabilities import C5_CAPABILITIES, c5_capability_block_reason

            capability = next((item for item in C5_CAPABILITIES if item.target == target), None)
            block_reason = c5_capability_block_reason(db, site_id, capability) if capability is not None else None
            if block_reason:
                action.state = "failed"
                action.resolved_at = current
                action.payload = {**action.payload, "error": block_reason}
            else:
                on = not command.endswith(("_off", "_close"))
                try:
                    requested_value = int(action.payload.get("value"))
                except (TypeError, ValueError):
                    requested_value = 100 if on else 0
                queued = queue_site_command(
                    db,
                    site_id,
                    SiteCommandRequest(
                        target=target,
                        value=max(0, min(100, requested_value)),
                        reason=str(action.payload.get("reason") or "C5 device-control confirmation"),
                        source="edge_voice",
                    ),
                    assistant_action_id=action.id,
                )
                action.state = "confirmed"
                action.resolved_at = current
                action.payload = {**action.payload, "command_id": queued.command_id}
    elif action.action_type == "smart_control":
        smart_key = str(action.payload.get("smart_key") or action.payload.get("key") or "")
        operation = str(action.payload.get("operation") or "")
        if smart_key != "light" or operation not in {"set_manual", "update_manual"}:
            action.state = "failed"
            action.resolved_at = current
            action.payload = {**action.payload, "error": "Only the real grow-light control is available."}
        else:
            try:
                requested_value = int(action.payload.get("value"))
            except (TypeError, ValueError):
                action.state = "failed"
                action.resolved_at = current
                action.payload = {**action.payload, "error": "A grow-light brightness value from 0 to 100 is required."}
            else:
                assistant_session = db.get(EdgeAssistantSession, action.session_id)
                source = "edge_voice" if assistant_session is None or assistant_session.channel == "edge_text" else "web_manual"
                queued = queue_site_command(
                    db,
                    site_id,
                    SiteCommandRequest(
                        target="grow_light",
                        value=max(0, min(100, requested_value)),
                        reason=str(action.payload.get("reason") or "assistant grow-light confirmation"),
                        source=source,
                    ),
                    assistant_action_id=action.id,
                )
                action.state = "confirmed"
                action.resolved_at = current
                action.payload = {**action.payload, "command_id": queued.command_id}
    elif action.action_type == "send_position":
        result_id = str(action.payload.get("result_id") or "")
        stored_result = take_position_result(result_id)
        if stored_result is None:
            action.state = "failed"
            action.resolved_at = current
            action.payload = {**action.payload, "error": "定位结果已过期，请重新查看摄像头。"}
        else:
            candidate, _captured_at = stored_result
            device_id = str(action.payload.get("device_id") or s3_device_id())
            queued = queue_command(
                db,
                DeviceCommandRequest(
                    device_id=device_id,
                    command="target_position",
                    value=1,
                    reason="发送目标地面极坐标",
                    position={
                        "ground_range_mm": candidate.ground_range_mm,
                        "bearing_deg": candidate.bearing_deg,
                    },
                ),
            )
            action.state = "confirmed"
            action.resolved_at = current
            action.payload = {**action.payload, "command_id": int(queued.command.get("id", 0) or 0)}
    elif action.action_type == "water_gun_target":
        from c5_assistant_capabilities import c5_water_gun_block_reason

        block_reason = c5_water_gun_block_reason(db, site_id)
        if block_reason:
            action.state = "failed"
            action.resolved_at = current
            action.payload = {**action.payload, "error": block_reason}
            db.commit()
            response = _action_response(action)
            site_event_bus.publish(site_id, "assistant_action", response.model_dump(mode="json"))
            logger.info("C5 assistant stage=dispatch_blocked action_id=%s target=water_gun", action.id)
            return response
        target = _assistant_water_gun_target(action)
        if target is None:
            action.state = "failed"
            action.resolved_at = current
            error_message = (
                "手动水枪目标无效，请重新设置距离和方位。"
                if isinstance(action.payload.get("manual_target"), dict)
                else "定位结果已过期，请重新查看摄像头。"
            )
            action.payload = {**action.payload, "error": error_message}
        else:
            ground_range_mm, bearing_deg, target_label, source = target
            spray_schedule = str(action.payload.get("spray_schedule") or "continuous")
            spray_duration_seconds = action.payload.get("spray_duration_seconds")
            state = water_gun_runtime.set_static(
                db,
                site_id,
                WaterGunStaticRequest(
                    ground_range_mm=ground_range_mm,
                    bearing_deg=bearing_deg,
                    device_id=s3_device_id(),
                    source=source,
                    target_label=target_label,
                    spray_enabled=True,
                    spray_schedule="timed" if spray_schedule == "timed" else "continuous",
                    spray_duration_seconds=(
                        int(spray_duration_seconds)
                        if spray_schedule == "timed" and spray_duration_seconds is not None
                        else None
                    ),
                    allow_target_change_while_spraying=True,
                ),
            )
            action.state = "confirmed"
            action.resolved_at = current
            action.payload = {
                **action.payload,
                "command_id": state.last_command_id,
                "water_gun": state.model_dump(mode="json"),
            }
    else:
        action.state = "failed"
        action.resolved_at = current
    choice_group = str(action.payload.get("choice_group") or "")
    if choice_group and action.state in {"confirmed", "executed"}:
        sibling_actions = db.scalars(
            select(EdgeAssistantAction).where(
                EdgeAssistantAction.message_id == action.message_id,
                EdgeAssistantAction.state == "pending",
                EdgeAssistantAction.id != action.id,
            )
        ).all()
        for sibling in sibling_actions:
            if str((sibling.payload or {}).get("choice_group") or "") == choice_group:
                sibling.state = "canceled"
                sibling.resolved_at = current
    db.commit()
    response = _action_response(action)
    logger.info(
        "C5 assistant stage=decision action_id=%s type=%s decision=%s state=%s",
        action.id,
        action.action_type,
        decision,
        action.state,
    )
    site_event_bus.publish(site_id, "assistant_action", response.model_dump(mode="json"))
    return response


def get_edge_conversation(db: Session, site_id: str, session_id: str | None = None) -> EdgeAssistantConversationResponse:
    if session_id is None:
        session = db.scalar(
            select(EdgeAssistantSession)
            .where(EdgeAssistantSession.site_id == site_id)
            .order_by(EdgeAssistantSession.updated_at.desc())
            .limit(1)
        )
        if session is None:
            return EdgeAssistantConversationResponse(session_id="", messages=[])
        session_id = session.id
    messages = db.scalars(
        select(EdgeAssistantMessage)
        .where(EdgeAssistantMessage.site_id == site_id, EdgeAssistantMessage.session_id == session_id)
        .order_by(EdgeAssistantMessage.created_at.asc())
    ).all()
    action_rows = db.scalars(
        select(EdgeAssistantAction).where(
            EdgeAssistantAction.site_id == site_id, EdgeAssistantAction.session_id == session_id
        )
    ).all()
    actions_by_message: dict[str, list[EdgeAssistantAction]] = {}
    for action in action_rows:
        actions_by_message.setdefault(action.message_id, []).append(action)
    return EdgeAssistantConversationResponse(
        session_id=session_id,
        messages=[_message_response(message, actions_by_message.get(message.id, [])) for message in messages],
    )
