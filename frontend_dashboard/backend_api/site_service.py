from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from assistant_service import assistant_chat
from schemas import AssistantChatRequest
from site_events import site_event_bus
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
ACTUATOR_KEYS = ("pump", "heater", "grow_light", "fan", "alarm", "curtain", "cooler", "ventilation", "co2_valve")
COMMAND_TTL_MS = 30_000
ACTION_TTL_MS = 30_000
HISTORY_SAMPLE_INTERVAL_MS = 10_000
HISTORY_RETENTION_MS = 24 * 60 * 60 * 1000
VISIBLE_HISTORY_SENSOR_KEYS = (
    "temperature_c",
    "illuminance_lux",
    "co2_ppm",
    "soil_moisture_pct",
)


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
        key: _actuator_state(actuator_input.get(key), supported_default=key in {"pump", "heater", "grow_light"})
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
            key: ActuatorState(supported=key in {"pump", "heater", "grow_light"}) for key in ACTUATOR_KEYS
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
    devices = {
        row.device_id: EdgeDeviceState(
            device_id=row.device_id,
            role=row.role,
            online=row.online,
            last_seen_at=row.last_seen_at,
            status=row.status or {},
        )
        for row in device_rows
    }
    return SiteState(
        site_id=site_id,
        updated_at=updated_at,
        sensors=sensors,
        quality=quality,
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
    site_event_bus.publish(record.site_id, "command_update", response.model_dump(mode="json"))
    return response


def command_wire_payload(record: SiteCommandRecord) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "command_id": record.command_id,
        "device_id": record.device_id,
        "site_id": record.site_id,
        "issued_at": record.created_at,
        "expires_at": record.expires_at,
        "source": record.source,
        "reason": record.reason,
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


def _store_message(
    db: Session,
    session: EdgeAssistantSession,
    role: str,
    channel: str,
    content: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> EdgeAssistantMessage:
    message = EdgeAssistantMessage(
        id=f"msg-{uuid.uuid4()}",
        session_id=session.id,
        site_id=session.site_id,
        role=role,
        channel=channel,
        content=content,
        created_at=now_ms(),
        message_metadata=metadata or {},
    )
    db.add(message)
    return message


def _deterministic_device_action(text: str) -> tuple[str, dict[str, Any]] | None:
    if "水泵" not in text and not any(word in text for word in ("浇水", "加水", "灌溉")):
        return None
    if any(word in text for word in ("关闭", "关掉", "停止", "停泵", "不要")):
        return "要关闭水泵吗？确认后执行。", {"command": "pump_off", "value": 0, "reason": "现场语音请求关闭水泵"}
    if any(word in text for word in ("打开", "开启", "浇水", "加水", "灌溉")):
        return "要打开水泵吗？确认后执行；水泵会持续运行，直到你明确关闭。", {
            "command": "pump_on",
            "value": 100,
            "reason": "现场语音请求打开水泵",
        }
    return None


def _latest_for_assistant(db: Session, site_id: str) -> dict[str, Any]:
    state = get_site_state(db, site_id)
    sensors = state.sensors
    return {
        "device_id": s3_device_id(),
        "timestamp": state.updated_at,
        "sensors": {
            "temperature": sensors.get("temperature_c"),
            "humidity": sensors.get("humidity_pct"),
            "pressure": sensors.get("pressure_kpa"),
            "gas_resistance": sensors.get("gas_resistance_ohm"),
            "light": sensors.get("illuminance_lux"),
            "co2": sensors.get("co2_ppm"),
            "soil_moisture": sensors.get("soil_moisture_pct"),
            "soil_ec": sensors.get("soil_ec_ms_cm"),
        },
    }


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
    return EdgeAssistantMessageResponse(
        id=message.id,
        session_id=message.session_id,
        site_id=message.site_id,
        role=message.role,
        channel=message.channel,
        content=message.content,
        created_at=message.created_at,
        actions=[_action_response(action) for action in actions],
    )


def create_edge_assistant_reply(db: Session, site_id: str, text: str, session_id: str | None, channel: str) -> EdgeAssistantMessageResponse:
    session = _ensure_session(db, site_id, session_id, channel)
    _store_message(db, session, "user", channel, text)
    deterministic = _deterministic_device_action(text)
    raw_actions: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    if deterministic is not None:
        reply_text, action_payload = deterministic
        raw_actions = [{"type": "device_command", "risk": "high", "payload": action_payload}]
    else:
        response = assistant_chat(AssistantChatRequest(question=text, latest=_latest_for_assistant(db, site_id)))
        reply_text = _brief_text(response.message.content)
        raw_actions = [action.model_dump(mode="json") for action in response.actions]
        references = [reference.model_dump(mode="json") for reference in response.references]

    assistant_message = _store_message(
        db,
        session,
        "assistant",
        "edge_text" if channel == "edge_text" else "web",
        _brief_text(reply_text) if channel == "edge_text" else reply_text,
        metadata={"references": references},
    )
    actions: list[EdgeAssistantAction] = []
    for raw_action in raw_actions[:3]:
        payload = raw_action.get("payload") if isinstance(raw_action.get("payload"), dict) else {}
        action = EdgeAssistantAction(
            id=f"action-{uuid.uuid4()}",
            session_id=session.id,
            site_id=site_id,
            message_id=assistant_message.id,
            action_type=str(raw_action.get("type") or "unknown"),
            risk=str(raw_action.get("risk") or "normal"),
            state="pending",
            payload=payload,
            created_at=now_ms(),
            expires_at=now_ms() + ACTION_TTL_MS,
        )
        db.add(action)
        actions.append(action)
    db.commit()
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
        action.state = "canceled"
        action.resolved_at = current
    elif action.action_type == "device_command":
        command = str(action.payload.get("command") or "")
        target_map = {"pump": "pump", "light": "grow_light", "heater": "heater"}
        target = target_map.get(command.rsplit("_", 1)[0])
        if target is None:
            action.state = "failed"
            action.resolved_at = current
        else:
            on = not command.endswith("_off")
            queued = queue_site_command(
                db,
                site_id,
                SiteCommandRequest(
                    target=target,
                    value=100 if on else 0,
                    reason=str(action.payload.get("reason") or "现场助手确认操作"),
                    source="edge_voice",
                ),
                assistant_action_id=action.id,
            )
            action.state = "confirmed"
            action.resolved_at = current
            action.payload = {**action.payload, "command_id": queued.command_id}
    else:
        action.state = "failed"
        action.resolved_at = current
    db.commit()
    response = _action_response(action)
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
