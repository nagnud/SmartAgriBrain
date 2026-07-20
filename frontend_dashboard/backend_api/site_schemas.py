from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


SiteCommandTarget = Literal["pump", "heater", "grow_light", "fan", "curtain", "alarm"]


class ActuatorState(BaseModel):
    supported: bool = False
    desired: int | None = Field(default=None, ge=0, le=100)
    actual: int | None = Field(default=None, ge=0, le=100)
    unit: Literal["percent"] = "percent"
    master_enabled: bool | None = None


class EdgeDeviceState(BaseModel):
    device_id: str
    role: Literal["sensor_actuator", "voice_display"]
    online: bool
    last_seen_at: int
    status: dict[str, Any] = Field(default_factory=dict)


class SiteState(BaseModel):
    schema_version: str = "1.0"
    site_id: str
    updated_at: int
    sensors: dict[str, float | None]
    quality: dict[str, str]
    sensor_display: dict[str, Literal["high", "low", "normal", "unavailable"]] = Field(default_factory=dict)
    actuators: dict[str, ActuatorState]
    devices: dict[str, EdgeDeviceState]


class SiteHistoryPoint(BaseModel):
    timestamp: int
    temperature: float | None = None
    light: float | None = None
    co2: float | None = None
    soil_moisture: float | None = None
    # These fields stay in the contract for future sensor expansion, but the
    # current Web pages intentionally do not render them.
    humidity: float | None = None
    gas_resistance: float | None = None
    soil_ec: float | None = None


class SiteCommandRequest(BaseModel):
    target: SiteCommandTarget
    value: int = Field(..., ge=0, le=100)
    reason: str = Field(default="", max_length=500)
    source: Literal["web_manual", "edge_voice", "smart_control"] = "web_manual"

    @model_validator(mode="after")
    def reject_smart_pump_control(self) -> "SiteCommandRequest":
        if self.target == "pump" and self.source == "smart_control":
            raise ValueError("水泵自动调控已暂停，当前由水枪控制")
        return self


class SiteCommandResponse(BaseModel):
    command_id: str
    site_id: str
    device_id: str
    target: str
    value: int
    state: Literal["queued", "dispatched", "succeeded", "failed", "expired"]
    created_at: int
    expires_at: int
    actual_value: int | None = None
    error: dict[str, Any] | None = None


class EdgeAssistantMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = Field(default=None, max_length=64)
    channel: Literal["web", "edge_text"] = "web"


class EdgeAssistantDecisionRequest(BaseModel):
    decision: Literal["confirm", "cancel"]


class EdgeAssistantActionResponse(BaseModel):
    id: str
    type: str
    risk: str
    state: str
    payload: dict[str, Any]
    expires_at: int


class EdgeAssistantMessageResponse(BaseModel):
    id: str
    session_id: str
    site_id: str
    role: Literal["user", "assistant"]
    channel: str
    content: str
    created_at: int
    actions: list[EdgeAssistantActionResponse] = Field(default_factory=list)
    next_input: Literal["none", "duration", "confirmation"] = "none"


class EdgeAssistantConversationResponse(BaseModel):
    session_id: str
    messages: list[EdgeAssistantMessageResponse]
