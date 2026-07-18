from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ConnectionState = Literal["connected", "disconnected", "warning"]
CommandState = Literal["queued", "dispatched", "succeeded", "failed"]


class SensorSnapshot(BaseModel):
    temperature: float = Field(..., ge=-80, le=100, allow_inf_nan=False)
    humidity: float = Field(..., ge=0, le=100, allow_inf_nan=False)
    pressure: float = Field(..., ge=0, le=2000, allow_inf_nan=False)
    gas_resistance: float = Field(..., ge=0, allow_inf_nan=False)
    light: float = Field(..., ge=0, allow_inf_nan=False)
    co2: float = Field(..., ge=0, allow_inf_nan=False)
    soil_moisture: float = Field(..., ge=0, le=100, allow_inf_nan=False)
    soil_ec: float = Field(..., ge=0, allow_inf_nan=False)


class DeviceRuntimeStatus(BaseModel):
    wifi: ConnectionState
    mqtt: ConnectionState
    fan: int = Field(..., ge=0, le=1)
    pump: int = Field(..., ge=0, le=1)
    light: int = Field(..., ge=0, le=1)
    alarm: int = Field(..., ge=0, le=1)
    curtain: int = Field(..., ge=0, le=1)


class TelemetryPayload(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=80)
    timestamp: int = Field(..., gt=0)
    sensors: SensorSnapshot
    status: DeviceRuntimeStatus


class TelemetryInPayload(TelemetryPayload):
    message_id: Optional[str] = Field(default=None, min_length=1, max_length=120)
    sequence: Optional[int] = Field(default=None, ge=0)


class TelemetryAcceptedResponse(BaseModel):
    success: bool = True
    record_id: int
    device_id: str
    timestamp: int


class HistoryPoint(BaseModel):
    timestamp: int
    temperature: float
    humidity: float
    gas_resistance: float
    light: float
    co2: float
    soil_moisture: float
    soil_ec: float


ALLOWED_COMMANDS = {
    "fan_on",
    "fan_off",
    "pump_on",
    "pump_off",
    "light_on",
    "light_off",
    "alarm_on",
    "alarm_off",
    "curtain_open",
    "curtain_close",
    "target_position",
}


class DeviceCommandRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    device_id: str = Field(..., min_length=1, max_length=80)
    command: str
    value: int = Field(..., ge=0, le=1)
    reason: str = Field(default="", max_length=1000)

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        command = value.strip().lower()
        if command not in ALLOWED_COMMANDS:
            raise ValueError("unsupported device command")
        return command


class CommandResult(BaseModel):
    success: bool
    message: str
    command: Dict[str, Any]
    executed_at: int
    status: DeviceRuntimeStatus


class QueuedCommand(BaseModel):
    command_id: int
    device_id: str
    command: str
    value: int
    reason: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)
    state: CommandState
    created_at: int
    dispatched_at: Optional[int] = None


class NextCommandResponse(BaseModel):
    command: Optional[QueuedCommand] = None


class CommandAckRequest(BaseModel):
    success: bool
    message: str = Field(default="", max_length=2000)
    status: Optional[DeviceRuntimeStatus] = None


class CommandAckResponse(BaseModel):
    command_id: int
    state: CommandState
    success: bool
    message: str
    executed_at: int


MetricKey = Literal[
    "temperature",
    "humidity",
    "light",
    "co2",
    "soil_moisture",
    "soil_ec",
    "gas_resistance",
]
AlarmState = Literal["open", "acknowledged", "resolved"]


class MetricTargetRange(BaseModel):
    min: float = Field(..., allow_inf_nan=False)
    max: float = Field(..., allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_order(self) -> "MetricTargetRange":
        if self.min > self.max:
            raise ValueError("target minimum cannot exceed maximum")
        return self


class AlarmTargetRanges(BaseModel):
    temperature: MetricTargetRange
    humidity: MetricTargetRange
    light: MetricTargetRange
    co2: MetricTargetRange
    soil_moisture: MetricTargetRange
    soil_ec: MetricTargetRange
    gas_resistance: MetricTargetRange


class AlarmSettingsUpdate(BaseModel):
    ranges: AlarmTargetRanges


class AlarmSettingsResponse(BaseModel):
    device_id: str
    configured: bool
    ranges: AlarmTargetRanges
    updated_at: Optional[str] = None


class AlarmRecordResponse(BaseModel):
    id: str
    device_id: str
    level: Literal["info", "warning", "danger"]
    title: str
    detail: str
    source: str
    timestamp: int
    state: AlarmState
    handled: bool
    handled_at: Optional[int] = None
    resolved_at: Optional[int] = None


class DeviceHealthResponse(BaseModel):
    device_id: str
    device_name: str
    online: bool
    transport: Literal["http", "mqtt"]
    last_seen_at: int
    last_telemetry_at: int
    offline_after_seconds: int
