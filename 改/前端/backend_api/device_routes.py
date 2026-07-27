from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from device_schemas import (
    AlarmRecordResponse,
    AlarmSettingsResponse,
    AlarmSettingsUpdate,
    CommandAckRequest,
    CommandAckResponse,
    CommandResult,
    DeviceCommandRequest,
    DeviceRuntimeStatus,
    DeviceHealthResponse,
    HistoryPoint,
    NextCommandResponse,
    TelemetryAcceptedResponse,
    TelemetryInPayload,
    TelemetryPayload,
)
from device_service import (
    DEFAULT_DEVICE_ID,
    CommandConflictError,
    DeviceNotFoundError,
    acknowledge_command,
    claim_next_command,
    get_history,
    latest_record,
    queue_command,
    record_payload,
    record_status,
    save_telemetry,
)
from monitoring_service import (
    acknowledge_alarm,
    apply_alarm_settings,
    get_alarm_settings,
    get_device_health as read_device_health,
    list_alarms,
)


router = APIRouter(prefix="/api/device", tags=["device"])


def not_found(error: DeviceNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(error))


@router.post("/telemetry", response_model=TelemetryAcceptedResponse)
def post_telemetry(payload: TelemetryInPayload, db: Session = Depends(get_db)) -> TelemetryAcceptedResponse:
    return save_telemetry(db, payload)


@router.get("/latest", response_model=TelemetryPayload)
def get_latest(
    device_id: str = Query(default=DEFAULT_DEVICE_ID, min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> TelemetryPayload:
    try:
        return record_payload(latest_record(db, device_id))
    except DeviceNotFoundError as error:
        raise not_found(error) from error


@router.get("/history", response_model=list[HistoryPoint])
def get_device_history(
    device_id: str = Query(default=DEFAULT_DEVICE_ID, min_length=1, max_length=80),
    limit: int = Query(default=36, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[HistoryPoint]:
    try:
        return get_history(db, device_id, limit)
    except DeviceNotFoundError as error:
        raise not_found(error) from error


@router.get("/status", response_model=DeviceRuntimeStatus)
def get_device_status(
    device_id: str = Query(default=DEFAULT_DEVICE_ID, min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> DeviceRuntimeStatus:
    try:
        return record_status(latest_record(db, device_id))
    except DeviceNotFoundError as error:
        raise not_found(error) from error


@router.get("/health", response_model=DeviceHealthResponse)
def get_device_health(
    device_id: str = Query(default=DEFAULT_DEVICE_ID, min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> DeviceHealthResponse:
    try:
        return read_device_health(db, device_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/alarm-settings", response_model=AlarmSettingsResponse)
def read_alarm_settings(
    device_id: str = Query(default=DEFAULT_DEVICE_ID, min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> AlarmSettingsResponse:
    return get_alarm_settings(db, device_id)


@router.put("/alarm-settings", response_model=AlarmSettingsResponse)
def write_alarm_settings(
    payload: AlarmSettingsUpdate,
    device_id: str = Query(default=DEFAULT_DEVICE_ID, min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> AlarmSettingsResponse:
    return apply_alarm_settings(db, device_id, payload.ranges)


@router.get("/alarms", response_model=list[AlarmRecordResponse])
def get_alarm_records(
    device_id: str = Query(default=DEFAULT_DEVICE_ID, min_length=1, max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
    state: str | None = Query(default=None, pattern="^(open|acknowledged|resolved)$"),
    db: Session = Depends(get_db),
) -> list[AlarmRecordResponse]:
    return list_alarms(db, device_id, limit, state)


@router.post("/alarms/{alarm_id}/ack", response_model=AlarmRecordResponse)
def post_alarm_ack(alarm_id: str, db: Session = Depends(get_db)) -> AlarmRecordResponse:
    try:
        return acknowledge_alarm(db, alarm_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/command", response_model=CommandResult)
def post_command(payload: DeviceCommandRequest, db: Session = Depends(get_db)) -> CommandResult:
    try:
        return queue_command(db, payload)
    except DeviceNotFoundError as error:
        raise not_found(error) from error


@router.get("/commands/next", response_model=NextCommandResponse)
def get_next_command(
    device_id: str = Query(default=DEFAULT_DEVICE_ID, min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> NextCommandResponse:
    return NextCommandResponse(command=claim_next_command(db, device_id))


@router.post("/commands/{command_id}/ack", response_model=CommandAckResponse)
def post_command_ack(
    command_id: int,
    payload: CommandAckRequest,
    db: Session = Depends(get_db),
) -> CommandAckResponse:
    try:
        return acknowledge_command(db, command_id, payload)
    except DeviceNotFoundError as error:
        raise not_found(error) from error
    except CommandConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
