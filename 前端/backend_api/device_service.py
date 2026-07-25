from __future__ import annotations

import os
import time
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from device_models import DeviceCommandRecord, TelemetryRecord
from device_schemas import (
    CommandAckRequest,
    CommandAckResponse,
    CommandResult,
    DeviceCommandRequest,
    DeviceRuntimeStatus,
    HistoryPoint,
    QueuedCommand,
    TelemetryAcceptedResponse,
    TelemetryInPayload,
    TelemetryPayload,
)
from monitoring_service import (
    add_telemetry_receipt,
    evaluate_environment_alarms,
    find_duplicate_record,
    mark_device_seen,
)


DEFAULT_DEVICE_ID = os.getenv("DEFAULT_DEVICE_ID", "greenhouse_001_s3")
S3_DEVICE_ID = os.getenv("S3_DEVICE_ID", "greenhouse_001_s3")
SECOND_TIMESTAMP_CUTOFF = 100_000_000_000


class DeviceNotFoundError(LookupError):
    pass


class CommandConflictError(RuntimeError):
    pass


def now_ms() -> int:
    return int(time.time() * 1000)


def normalize_timestamp(value: int) -> int:
    return value * 1000 if value < SECOND_TIMESTAMP_CUTOFF else value


def latest_record(db: Session, device_id: str) -> TelemetryRecord:
    record = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.device_id == device_id)
        .order_by(desc(TelemetryRecord.timestamp), desc(TelemetryRecord.id))
        .first()
    )
    if record is None:
        raise DeviceNotFoundError(f"device {device_id} has no telemetry")
    return record


def record_status(record: TelemetryRecord) -> DeviceRuntimeStatus:
    return DeviceRuntimeStatus(
        wifi=record.wifi,
        mqtt=record.mqtt,
        fan=record.fan,
        pump=record.pump,
        light=record.light_status,
        alarm=record.alarm,
        curtain=record.curtain,
    )


def record_payload(record: TelemetryRecord) -> TelemetryPayload:
    return TelemetryPayload(
        device_id=record.device_id,
        timestamp=record.timestamp,
        sensors={
            "temperature": record.temperature,
            "humidity": record.humidity,
            "pressure": record.pressure,
            "gas_resistance": record.gas_resistance,
            "light": record.light,
            "co2": record.co2,
            "soil_moisture": record.soil_moisture,
            "soil_ec": record.soil_ec,
        },
        status=record_status(record),
    )


def save_telemetry(
    db: Session,
    payload: TelemetryInPayload,
    transport: str = "http",
) -> TelemetryAcceptedResponse:
    duplicate = find_duplicate_record(db, payload.device_id, payload.message_id)
    if duplicate is not None:
        return TelemetryAcceptedResponse(
            record_id=duplicate.id,
            device_id=duplicate.device_id,
            timestamp=duplicate.timestamp,
        )

    timestamp = normalize_timestamp(payload.timestamp)
    sensors = payload.sensors
    status = payload.status
    record = TelemetryRecord(
        device_id=payload.device_id,
        timestamp=timestamp,
        temperature=sensors.temperature,
        humidity=sensors.humidity,
        pressure=sensors.pressure,
        gas_resistance=sensors.gas_resistance,
        light=sensors.light,
        co2=sensors.co2,
        soil_moisture=sensors.soil_moisture,
        soil_ec=sensors.soil_ec,
        wifi=status.wifi,
        mqtt=status.mqtt,
        fan=status.fan,
        pump=status.pump,
        light_status=status.light,
        alarm=status.alarm,
        curtain=status.curtain,
        received_at=now_ms(),
    )
    db.add(record)
    db.flush()
    add_telemetry_receipt(db, record, payload, transport)
    mark_device_seen(db, record.device_id, transport, telemetry_at=record.received_at)
    evaluate_environment_alarms(db, record)
    db.commit()
    db.refresh(record)
    return TelemetryAcceptedResponse(record_id=record.id, device_id=record.device_id, timestamp=record.timestamp)


def get_history(db: Session, device_id: str, limit: int) -> list[HistoryPoint]:
    records = (
        db.query(TelemetryRecord)
        .filter(TelemetryRecord.device_id == device_id)
        .order_by(desc(TelemetryRecord.timestamp), desc(TelemetryRecord.id))
        .limit(limit)
        .all()
    )
    if not records:
        raise DeviceNotFoundError(f"device {device_id} has no telemetry")
    return [
        HistoryPoint(
            timestamp=record.timestamp,
            temperature=record.temperature,
            humidity=record.humidity,
            gas_resistance=record.gas_resistance,
            light=record.light,
            co2=record.co2,
            soil_moisture=record.soil_moisture,
            soil_ec=record.soil_ec,
        )
        for record in reversed(records)
    ]


def queue_command(db: Session, payload: DeviceCommandRequest) -> CommandResult:
    try:
        current_status = record_status(latest_record(db, payload.device_id))
    except DeviceNotFoundError:
        if payload.command != "target_position" or payload.device_id != S3_DEVICE_ID:
            raise
        # The S3 reports through the site-state telemetry contract rather than
        # the legacy TelemetryRecord table. Position delivery still uses this
        # durable command queue, so return a neutral status for the queue result.
        current_status = DeviceRuntimeStatus(
            wifi="warning",
            mqtt="warning",
            fan=0,
            pump=0,
            light=0,
            alarm=0,
            curtain=0,
        )
    created_at = now_ms()
    command_payload = payload.model_dump()
    record = DeviceCommandRecord(
        device_id=payload.device_id,
        command=payload.command,
        value=payload.value,
        reason=payload.reason,
        payload=command_payload,
        status="queued",
        created_at=created_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    response_payload = {**command_payload, "id": record.id}
    return CommandResult(
        success=True,
        message=f"指令已进入待执行队列（编号 {record.id}），等待设备拉取并回传执行结果。",
        command=response_payload,
        executed_at=created_at,
        status=current_status,
    )


def to_queued_command(record: DeviceCommandRecord) -> QueuedCommand:
    return QueuedCommand(
        command_id=record.id,
        device_id=record.device_id,
        command=record.command,
        value=record.value,
        reason=record.reason,
        payload=record.payload or {},
        state=record.status,
        created_at=record.created_at,
        dispatched_at=record.dispatched_at,
    )


def claim_next_command(db: Session, device_id: str, consumer_transport: str = "http") -> Optional[QueuedCommand]:
    configured_transport = os.getenv("DEVICE_COMMAND_TRANSPORT", "mqtt").strip().lower()
    configured_transport = "mqtt" if configured_transport == "mqtt" else "http"
    if consumer_transport != configured_transport:
        return None
    for _ in range(3):
        record = (
            db.query(DeviceCommandRecord)
            .filter(DeviceCommandRecord.device_id == device_id, DeviceCommandRecord.status == "queued")
            .order_by(DeviceCommandRecord.id)
            .first()
        )
        if record is None:
            return None

        dispatched_at = now_ms()
        updated = (
            db.query(DeviceCommandRecord)
            .filter(DeviceCommandRecord.id == record.id, DeviceCommandRecord.status == "queued")
            .update(
                {DeviceCommandRecord.status: "dispatched", DeviceCommandRecord.dispatched_at: dispatched_at},
                synchronize_session=False,
            )
        )
        if updated == 1:
            db.commit()
            claimed = db.get(DeviceCommandRecord, record.id)
            return to_queued_command(claimed)
        db.rollback()
    return None


def acknowledge_command(db: Session, command_id: int, payload: CommandAckRequest) -> CommandAckResponse:
    record = db.get(DeviceCommandRecord, command_id)
    if record is None:
        raise DeviceNotFoundError(f"command {command_id} does not exist")

    target_state = "succeeded" if payload.success else "failed"
    if record.status in {"succeeded", "failed"}:
        if record.status != target_state:
            raise CommandConflictError("command already has a different final result")
        return CommandAckResponse(
            command_id=record.id,
            state=record.status,
            success=bool(record.execution_success),
            message=record.result_message,
            executed_at=record.executed_at or record.created_at,
        )
    if record.status != "dispatched":
        raise CommandConflictError("command must be claimed before it can be acknowledged")

    record.status = target_state
    record.executed_at = now_ms()
    record.execution_success = payload.success
    record.result_message = payload.message
    record.reported_status = payload.status.model_dump() if payload.status is not None else None
    db.commit()
    db.refresh(record)
    return CommandAckResponse(
        command_id=record.id,
        state=record.status,
        success=payload.success,
        message=record.result_message,
        executed_at=record.executed_at,
    )
