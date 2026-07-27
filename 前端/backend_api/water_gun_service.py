from __future__ import annotations

import math
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from device_models import DeviceCommandRecord
from device_schemas import DeviceCommandRequest
from device_service import queue_command
from site_events import site_event_bus


Mode = Literal["static", "dynamic"]
Source = Literal["manual", "vision"]
SpraySchedule = Literal["continuous", "timed"]
StopReason = Literal["idle", "manual", "timed_complete", "target_changed", "mode_changed", "dynamic_timeout"]

# Web sends a heartbeat every second. A dry-tracking heartbeat only keeps the
# backend session alive; when the pump is running, it also becomes an ESP32
# keepalive so the device can enforce its independent three-second fail-safe.
DYNAMIC_INTERVAL_MS = 1_000
DYNAMIC_TIMEOUT_MS = 3_000
MANUAL_FORWARD_MAX_MM = 1_200.0
MANUAL_HALF_WIDTH_MM = 1_200.0

# Pump calibration copied from 改/前端. The measured result uses two linear
# sections because the low-duty response differs from the normal working range.
# Percent values are the PWM duty sent to the ESP32; distances are centimetres.
PUMP_MIN_PERCENT = 24.0
PUMP_MAX_PERCENT = 100.0
PUMP_LOW_SECTION_MAX_PERCENT = 30.0
PUMP_LOW_SECTION_MAX_DISTANCE_CM = 24.26
PUMP_LOW_DISTANCE_SLOPE = 3.9937
PUMP_LOW_DISTANCE_INTERCEPT = -95.5466
PUMP_HIGH_DISTANCE_SLOPE = 1.3657
PUMP_HIGH_DISTANCE_INTERCEPT = -16.7069
logger = logging.getLogger(__name__)


class WaterGunTarget(BaseModel):
    # Keep the REST boundary identical to the ESP32 parser. Accepting a target
    # here that the device later rejects makes the Web marker diverge from the
    # physical nozzle position.
    ground_range_mm: float = Field(ge=300, le=1_200)
    # The ESP32 maps the complete supported bearing range linearly to the
    # horizontal SG90 command range: -90 -> 0, 0 -> 90, +90 -> 180 degrees.
    bearing_deg: float = Field(ge=-90, le=90)


class WaterGunStaticRequest(WaterGunTarget):
    device_id: str = Field(default="greenhouse_001_s3", min_length=1, max_length=80)
    source: Source = "manual"
    target_label: str = Field(default="", max_length=120)
    spray_enabled: bool | None = None
    spray_schedule: SpraySchedule = "continuous"
    spray_duration_seconds: int | None = Field(default=None, ge=1, le=86_399)
    allow_target_change_while_spraying: bool = False

    @model_validator(mode="after")
    def validate_spray_schedule(self) -> "WaterGunStaticRequest":
        if self.spray_schedule == "timed" and self.spray_duration_seconds is None:
            raise ValueError("定时喷射必须设置 1 秒至 23 小时 59 分 59 秒的时长。")
        if self.spray_schedule == "continuous":
            self.spray_duration_seconds = None
        return self


class WaterGunPreviewRequest(WaterGunStaticRequest):
    pass


class WaterGunDynamicStartRequest(WaterGunTarget):
    device_id: str = Field(default="greenhouse_001_s3", min_length=1, max_length=80)
    source: Source = "manual"
    target_label: str = Field(default="", max_length=120)
    spray_enabled: bool = False


class WaterGunDynamicUpdateRequest(WaterGunTarget):
    session_id: str = Field(min_length=1, max_length=80)
    # Deprecated compatibility input. The backend owns the MQTT sequence
    # because heartbeat and target updates share one device-visible stream.
    # Ignoring a browser-provided value removes the heartbeat/update race.
    sequence: int | None = Field(default=None, ge=1)


class WaterGunHeartbeatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)


class WaterGunDynamicSprayRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    spray_enabled: bool


class WaterGunStopRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    keep_spraying: bool = False


class WaterGunStateResponse(BaseModel):
    site_id: str
    device_id: str
    mode: Mode
    ground_range_mm: float
    bearing_deg: float
    spray_enabled: bool
    source: Source
    target_label: str = ""
    session_id: str | None = None
    sequence: int = 0
    updated_at: int
    last_command_id: int | None = None
    timed_out: bool = False
    pump_control_percent: float = 0
    spray_schedule: SpraySchedule = "continuous"
    spray_duration_seconds: int | None = None
    spray_ends_at: int | None = None
    remaining_seconds: int | None = None
    stop_reason: StopReason = "idle"


@dataclass
class _WaterGunState:
    site_id: str
    device_id: str
    mode: Mode = "static"
    ground_range_mm: float = 600.0
    bearing_deg: float = 0.0
    spray_enabled: bool = False
    source: Source = "manual"
    target_label: str = ""
    session_id: str | None = None
    sequence: int = 0
    updated_at: int = 0
    last_heartbeat_at: int = 0
    last_published_at: int = 0
    last_command_id: int | None = None
    pending: bool = False
    timed_out: bool = False
    spray_schedule: SpraySchedule = "continuous"
    spray_duration_seconds: int | None = None
    spray_ends_at: int | None = None
    stop_reason: StopReason = "idle"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _default_device_id() -> str:
    return os.getenv("S3_DEVICE_ID", "greenhouse_001_s3").strip() or "greenhouse_001_s3"


def pwmToDistance(pwmPercent: float) -> float:
    """Convert pump PWM duty percent to the calibrated spray distance in cm."""
    # Clamp the input to the measured operating interval. A duty below 24%
    # cannot be represented reliably by this calibration; a duty above 100%
    # is not a valid PWM command.
    pwm = max(PUMP_MIN_PERCENT, min(PUMP_MAX_PERCENT, float(pwmPercent)))
    if pwm <= PUMP_LOW_SECTION_MAX_PERCENT:
        return PUMP_LOW_DISTANCE_SLOPE * pwm + PUMP_LOW_DISTANCE_INTERCEPT
    return PUMP_HIGH_DISTANCE_SLOPE * pwm + PUMP_HIGH_DISTANCE_INTERCEPT


def distanceToPwm(distanceCm: float) -> float:
    """Convert requested spray distance in cm to calibrated pump PWM duty."""
    # REST and MQTT continue to use millimetres. This helper deliberately uses
    # centimetres so its parameters remain identical to the measured model in
    # 改/前端 and can be checked directly against the original calibration.
    distance = max(0.0, float(distanceCm))
    if distance <= PUMP_LOW_SECTION_MAX_DISTANCE_CM:
        pwm = (distance - PUMP_LOW_DISTANCE_INTERCEPT) / PUMP_LOW_DISTANCE_SLOPE
    else:
        pwm = (distance - PUMP_HIGH_DISTANCE_INTERCEPT) / PUMP_HIGH_DISTANCE_SLOPE
    return max(PUMP_MIN_PERCENT, min(PUMP_MAX_PERCENT, pwm))


def _pump_control_percent(state: _WaterGunState) -> float:
    if not state.spray_enabled:
        return 0.0
    # Convert the existing millimetre target to centimetres only for the local
    # calibration calculation. The externally visible target value is unchanged.
    return distanceToPwm(state.ground_range_mm / 10.0)


def _manual_target_in_bounds(target: WaterGunTarget) -> bool:
    radians = math.radians(target.bearing_deg)
    right = target.ground_range_mm * math.sin(radians)
    forward = target.ground_range_mm * math.cos(radians)
    return (
        forward >= -0.001
        and forward <= MANUAL_FORWARD_MAX_MM + 0.001
        and abs(right) <= MANUAL_HALF_WIDTH_MM + 0.001
    )


def _response(state: _WaterGunState) -> WaterGunStateResponse:
    remaining_seconds = None
    if state.spray_enabled and state.spray_schedule == "timed" and state.spray_ends_at is not None:
        remaining_seconds = max(0, math.ceil((state.spray_ends_at - _now_ms()) / 1000))
    return WaterGunStateResponse(
        site_id=state.site_id,
        device_id=state.device_id,
        mode=state.mode,
        ground_range_mm=round(state.ground_range_mm, 1),
        bearing_deg=round(state.bearing_deg, 1),
        spray_enabled=state.spray_enabled,
        source=state.source,
        target_label=state.target_label,
        session_id=state.session_id,
        sequence=state.sequence,
        updated_at=state.updated_at,
        last_command_id=state.last_command_id,
        timed_out=state.timed_out,
        pump_control_percent=round(_pump_control_percent(state), 1),
        spray_schedule=state.spray_schedule,
        spray_duration_seconds=state.spray_duration_seconds,
        spray_ends_at=state.spray_ends_at,
        remaining_seconds=remaining_seconds,
        stop_reason=state.stop_reason,
    )


class WaterGunRuntime:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, _WaterGunState] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="water-gun-runtime", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def _state(self, site_id: str) -> _WaterGunState:
        state = self._states.get(site_id)
        if state is None:
            current = _now_ms()
            state = _WaterGunState(
                site_id=site_id,
                device_id=_default_device_id(),
                updated_at=current,
                last_heartbeat_at=current,
            )
            self._states[site_id] = state
        return state

    def read(self, site_id: str) -> WaterGunStateResponse:
        with self._lock:
            return _response(self._state(site_id))

    @staticmethod
    def _publish(response: WaterGunStateResponse) -> None:
        site_event_bus.publish(response.site_id, "water_gun", response.model_dump(mode="json"))

    def set_preview(self, site_id: str, request: WaterGunPreviewRequest) -> WaterGunStateResponse:
        if request.source == "manual" and not _manual_target_in_bounds(request):
            raise ValueError("手动目标超出前方 1200 mm、左右各 1200 mm 的可操作范围。")
        current = _now_ms()
        with self._lock:
            state = self._state(site_id)
            state.device_id = request.device_id
            state.mode = "static"
            state.ground_range_mm = request.ground_range_mm
            state.bearing_deg = request.bearing_deg
            state.source = request.source
            state.target_label = request.target_label.strip()
            if request.spray_enabled is not None:
                state.spray_enabled = request.spray_enabled
            state.spray_schedule = request.spray_schedule
            state.spray_duration_seconds = request.spray_duration_seconds
            state.spray_ends_at = (
                current + request.spray_duration_seconds * 1000
                if state.spray_enabled and request.spray_schedule == "timed" and request.spray_duration_seconds
                else None
            )
            state.stop_reason = "idle" if state.spray_enabled else "manual"
            state.session_id = None
            state.sequence += 1
            state.updated_at = current
            state.last_heartbeat_at = current
            state.pending = False
            state.timed_out = False
            response = _response(state)
        self._publish(response)
        return response

    def set_static(self, db: Session, site_id: str, request: WaterGunStaticRequest) -> WaterGunStateResponse:
        if request.source == "manual" and not _manual_target_in_bounds(request):
            raise ValueError("手动目标超出前方 1200 mm、左右各 1200 mm 的可操作范围。")
        current = _now_ms()
        with self._lock:
            state = self._state(site_id)
            previous = replace(state)
            target_changed = (
                abs(state.ground_range_mm - request.ground_range_mm) > 0.05
                or abs(state.bearing_deg - request.bearing_deg) > 0.05
                or state.source != request.source
                or state.target_label != request.target_label.strip()
            )
            state.device_id = request.device_id
            state.mode = "static"
            state.ground_range_mm = request.ground_range_mm
            state.bearing_deg = request.bearing_deg
            state.source = request.source
            state.target_label = request.target_label.strip()
            if request.spray_enabled is not None:
                state.spray_enabled = request.spray_enabled
            state.spray_schedule = request.spray_schedule
            state.spray_duration_seconds = request.spray_duration_seconds
            if (
                target_changed
                and previous.spray_enabled
                and not request.allow_target_change_while_spraying
            ):
                state.spray_enabled = False
                state.spray_schedule = "continuous"
                state.spray_duration_seconds = None
            state.spray_ends_at = (
                current + request.spray_duration_seconds * 1000
                if state.spray_enabled and request.spray_schedule == "timed" and request.spray_duration_seconds
                else None
            )
            if state.spray_enabled:
                state.stop_reason = "idle"
            elif target_changed and previous.spray_enabled:
                state.stop_reason = "target_changed"
            elif previous.spray_enabled:
                state.stop_reason = "manual"
            elif target_changed:
                state.stop_reason = "target_changed"
            state.session_id = None
            state.sequence += 1
            state.updated_at = current
            state.last_heartbeat_at = current
            state.pending = False
            state.timed_out = False
            try:
                state.last_command_id = self._queue_state(db, state, "静态水枪目标确认")
            except Exception:
                self._states[site_id] = previous
                raise
            response = _response(state)
        self._publish(response)
        return response

    def start_dynamic(self, db: Session, site_id: str, request: WaterGunDynamicStartRequest) -> WaterGunStateResponse:
        if request.source == "manual" and not _manual_target_in_bounds(request):
            raise ValueError("手动目标超出前方 1200 mm、左右各 1200 mm 的可操作范围。")
        current = _now_ms()
        with self._lock:
            state = self._state(site_id)
            previous = replace(state)
            state.device_id = request.device_id
            state.mode = "dynamic"
            state.ground_range_mm = request.ground_range_mm
            state.bearing_deg = request.bearing_deg
            state.spray_enabled = request.spray_enabled
            state.source = request.source
            state.target_label = request.target_label.strip()
            state.spray_schedule = "continuous"
            state.spray_duration_seconds = None
            state.spray_ends_at = None
            state.stop_reason = "idle" if request.spray_enabled else "manual"
            state.session_id = f"water-gun-{uuid.uuid4().hex}"
            state.sequence = 1
            state.updated_at = current
            state.last_heartbeat_at = current
            state.last_published_at = current
            state.pending = False
            state.timed_out = False
            try:
                state.last_command_id = self._queue_state(
                    db,
                    state,
                    "进入水枪动态喷射模拟" if request.spray_enabled else "进入水枪动态移动模拟，保持关闭喷水",
                )
            except Exception:
                self._states[site_id] = previous
                raise
            response = _response(state)
        self._publish(response)
        return response

    def update_dynamic(self, site_id: str, request: WaterGunDynamicUpdateRequest) -> WaterGunStateResponse:
        if not _manual_target_in_bounds(request):
            raise ValueError("动态目标超出手动可操作范围。")
        current = _now_ms()
        with self._lock:
            state = self._state(site_id)
            if state.mode != "dynamic" or state.session_id != request.session_id:
                raise LookupError("动态控制会话不存在或已经结束。")
            state.ground_range_mm = request.ground_range_mm
            state.bearing_deg = request.bearing_deg
            # Heartbeats and target changes must use one monotonic counter.
            # Only this locked backend state may allocate the next value.
            state.sequence += 1
            state.updated_at = current
            state.last_heartbeat_at = current
            state.pending = True
            response = _response(state)
        self._publish(response)
        return response

    def heartbeat(self, db: Session, site_id: str, request: WaterGunHeartbeatRequest) -> WaterGunStateResponse:
        """Refresh a dynamic session and, only while spraying, queue a device keepalive.

        When spray_enabled is false, the servo must hold its last commanded
        position without receiving the same target once per second. In that
        state this method updates only backend liveness timestamps.

        When spray_enabled is true, the browser heartbeat must also reach the
        ESP32. Advancing the sequence and marking the current state pending
        lets the device refresh its independent three-second pump watchdog.
        The ESP32 target de-duplication path keeps the unchanged servo PWM.
        """
        with self._lock:
            state = self._state(site_id)
            if state.mode != "dynamic" or state.session_id != request.session_id:
                raise LookupError("动态控制会话不存在或已经结束。")
            current = _now_ms()
            state.updated_at = current
            state.last_heartbeat_at = current
            if state.spray_enabled:
                state.sequence += 1
                state.pending = True
            response = _response(state)
        self._publish(response)
        return response

    def set_dynamic_spray(
        self,
        db: Session,
        site_id: str,
        request: WaterGunDynamicSprayRequest,
    ) -> WaterGunStateResponse:
        current = _now_ms()
        with self._lock:
            state = self._state(site_id)
            if state.mode != "dynamic" or state.session_id != request.session_id:
                raise LookupError("动态控制会话不存在或已经结束。")
            previous = replace(state)
            state.spray_enabled = request.spray_enabled
            state.sequence += 1
            state.updated_at = current
            state.last_heartbeat_at = current
            state.pending = False
            state.spray_schedule = "continuous"
            state.spray_duration_seconds = None
            state.spray_ends_at = None
            state.stop_reason = "idle" if request.spray_enabled else "manual"
            try:
                state.last_command_id = self._queue_state(
                    db,
                    state,
                    "动态模式开启水枪喷射模拟" if request.spray_enabled else "动态模式关闭水枪喷射模拟",
                )
            except Exception:
                self._states[site_id] = previous
                raise
            response = _response(state)
        self._publish(response)
        return response

    def stop_dynamic(self, db: Session, site_id: str, request: WaterGunStopRequest) -> WaterGunStateResponse:
        current = _now_ms()
        with self._lock:
            state = self._state(site_id)
            if state.mode != "dynamic" or state.session_id != request.session_id:
                raise LookupError("动态控制会话不存在或已经结束。")
            previous = replace(state)
            state.mode = "static"
            state.spray_enabled = request.keep_spraying
            state.spray_schedule = "continuous"
            state.spray_duration_seconds = None
            state.spray_ends_at = None
            state.stop_reason = "idle" if request.keep_spraying else "mode_changed"
            state.session_id = None
            state.sequence += 1
            state.updated_at = current
            state.last_heartbeat_at = current
            state.pending = False
            state.timed_out = False
            reason = "保持目标并转为静态喷射模拟" if request.keep_spraying else "停止水枪喷射并保留目标"
            try:
                state.last_command_id = self._queue_state(db, state, reason)
            except Exception:
                self._states[site_id] = previous
                raise
            response = _response(state)
        self._publish(response)
        return response

    def _queue_state(self, db: Session, state: _WaterGunState, reason: str) -> int | None:
        water_gun = {
            "mode": state.mode,
            "spray_enabled": state.spray_enabled,
            "pump_control_percent": round(_pump_control_percent(state), 1),
            "session_id": state.session_id,
            "sequence": state.sequence,
            "spray_schedule": state.spray_schedule,
            "spray_duration_seconds": state.spray_duration_seconds,
            "spray_ends_at": state.spray_ends_at,
        }
        position = {
            "ground_range_mm": round(state.ground_range_mm, 1),
            "bearing_deg": round(state.bearing_deg, 1),
        }
        if state.session_id:
            queued_records = db.scalars(
                select(DeviceCommandRecord).where(
                    DeviceCommandRecord.device_id == state.device_id,
                    DeviceCommandRecord.command == "target_position",
                    DeviceCommandRecord.status == "queued",
                ).order_by(DeviceCommandRecord.id.desc())
            ).all()
            for record in queued_records:
                payload = record.payload if isinstance(record.payload, dict) else {}
                existing = payload.get("water_gun") if isinstance(payload, dict) else None
                if isinstance(existing, dict) and existing.get("session_id") == state.session_id:
                    record.payload = {
                        "device_id": state.device_id,
                        "command": "target_position",
                        "value": 1,
                        "reason": reason,
                        "position": position,
                        "water_gun": water_gun,
                    }
                    record.reason = reason
                    record.created_at = _now_ms()
                    db.commit()
                    return record.id
        queued = queue_command(
            db,
            DeviceCommandRequest(
                device_id=state.device_id,
                command="target_position",
                value=1,
                reason=reason,
                position=position,
                water_gun=water_gun,
            ),
        )
        return int(queued.command.get("id", 0) or 0)

    def _run(self) -> None:
        while not self._stop_event.wait(0.05):
            current = _now_ms()
            publish_sites: list[str] = []
            timeout_sites: list[str] = []
            timed_stop_sites: list[str] = []
            with self._lock:
                for site_id, state in self._states.items():
                    if (
                        state.mode == "static"
                        and state.spray_enabled
                        and state.spray_schedule == "timed"
                        and state.spray_ends_at is not None
                        and current >= state.spray_ends_at
                    ):
                        timed_stop_sites.append(site_id)
                        continue
                    if state.mode != "dynamic":
                        continue
                    if current - state.last_heartbeat_at > DYNAMIC_TIMEOUT_MS:
                        timeout_sites.append(site_id)
                    elif state.pending and current - state.last_published_at >= DYNAMIC_INTERVAL_MS:
                        state.pending = False
                        state.last_published_at = current
                        publish_sites.append(site_id)
            for site_id in publish_sites:
                try:
                    with SessionLocal() as db:
                        with self._lock:
                            state = self._states.get(site_id)
                            if state is None or state.mode != "dynamic":
                                continue
                            state.last_command_id = self._queue_state(db, state, "水枪动态目标更新")
                            response = _response(state)
                        self._publish(response)
                except Exception:
                    logger.exception("Unable to queue dynamic water-gun target for %s", site_id)
                    with self._lock:
                        state = self._states.get(site_id)
                        if state is not None and state.mode == "dynamic":
                            state.pending = True
            for site_id in timed_stop_sites:
                try:
                    with SessionLocal() as db:
                        with self._lock:
                            state = self._states.get(site_id)
                            if (
                                state is None
                                or state.mode != "static"
                                or not state.spray_enabled
                                or state.spray_schedule != "timed"
                                or state.spray_ends_at is None
                                or current < state.spray_ends_at
                            ):
                                continue
                            previous = replace(state)
                            state.spray_enabled = False
                            state.spray_ends_at = None
                            state.sequence += 1
                            state.updated_at = current
                            state.stop_reason = "timed_complete"
                            try:
                                state.last_command_id = self._queue_state(db, state, "定时喷射结束，自动停止水枪")
                            except Exception:
                                self._states[site_id] = previous
                                raise
                            response = _response(state)
                        self._publish(response)
                except Exception:
                    logger.exception("Unable to queue timed water-gun stop for %s", site_id)
            for site_id in timeout_sites:
                try:
                    with SessionLocal() as db:
                        with self._lock:
                            state = self._states.get(site_id)
                            if state is None or state.mode != "dynamic":
                                continue
                            state.mode = "static"
                            state.spray_enabled = False
                            state.session_id = None
                            state.sequence += 1
                            state.updated_at = current
                            state.pending = False
                            state.timed_out = True
                            state.spray_schedule = "continuous"
                            state.spray_duration_seconds = None
                            state.spray_ends_at = None
                            state.stop_reason = "dynamic_timeout"
                            state.last_command_id = self._queue_state(db, state, "动态会话超时，自动停止水泵")
                            response = _response(state)
                        self._publish(response)
                except Exception:
                    logger.exception("Unable to queue water-gun timeout stop for %s", site_id)


water_gun_runtime = WaterGunRuntime()
