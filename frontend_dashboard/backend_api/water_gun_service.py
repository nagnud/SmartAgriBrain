from __future__ import annotations

import math
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from device_models import DeviceCommandRecord
from device_schemas import DeviceCommandRequest
from device_service import queue_command
from site_events import site_event_bus


Mode = Literal["static", "dynamic"]
Source = Literal["manual", "vision"]

DYNAMIC_INTERVAL_MS = 200
DYNAMIC_TIMEOUT_MS = 3_000
MANUAL_FORWARD_MAX_MM = 1_200.0
MANUAL_HALF_WIDTH_MM = 1_200.0
PUMP_FULL_SCALE_RANGE_MM = 1_700.0
logger = logging.getLogger(__name__)


class WaterGunTarget(BaseModel):
    ground_range_mm: float = Field(ge=0, le=1_000_000)
    bearing_deg: float = Field(ge=-180, le=180)


class WaterGunStaticRequest(WaterGunTarget):
    device_id: str = Field(default="greenhouse_001_s3", min_length=1, max_length=80)
    source: Source = "manual"
    target_label: str = Field(default="", max_length=120)
    spray_enabled: bool | None = None


class WaterGunPreviewRequest(WaterGunStaticRequest):
    pass


class WaterGunDynamicStartRequest(WaterGunTarget):
    device_id: str = Field(default="greenhouse_001_s3", min_length=1, max_length=80)
    source: Source = "manual"
    target_label: str = Field(default="", max_length=120)


class WaterGunDynamicUpdateRequest(WaterGunTarget):
    session_id: str = Field(min_length=1, max_length=80)
    sequence: int = Field(ge=1)


class WaterGunHeartbeatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)


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
    simulation_only: bool = True
    pump_control_percent: float = 0


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


def _now_ms() -> int:
    return int(time.time() * 1000)


def _default_device_id() -> str:
    return os.getenv("S3_DEVICE_ID", "greenhouse_001_s3").strip() or "greenhouse_001_s3"


def _simulation_only() -> bool:
    return os.getenv("WATER_GUN_SIMULATION_ONLY", "true").strip().lower() not in {"0", "false", "no", "off"}


def _pump_control_percent(state: _WaterGunState) -> float:
    if not state.spray_enabled:
        return 0.0
    return max(0.0, min(100.0, state.ground_range_mm / PUMP_FULL_SCALE_RANGE_MM * 100.0))


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
        simulation_only=_simulation_only(),
        pump_control_percent=round(_pump_control_percent(state), 1),
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
            state.device_id = request.device_id
            state.mode = "static"
            state.ground_range_mm = request.ground_range_mm
            state.bearing_deg = request.bearing_deg
            state.source = request.source
            state.target_label = request.target_label.strip()
            if request.spray_enabled is not None:
                state.spray_enabled = request.spray_enabled
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
            state.spray_enabled = True
            state.source = request.source
            state.target_label = request.target_label.strip()
            state.session_id = f"water-gun-{uuid.uuid4().hex}"
            state.sequence = 1
            state.updated_at = current
            state.last_heartbeat_at = current
            state.last_published_at = current
            state.pending = False
            state.timed_out = False
            try:
                state.last_command_id = self._queue_state(db, state, "进入水枪动态喷射模拟")
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
            if request.sequence <= state.sequence:
                raise ValueError("动态目标序号必须递增。")
            state.ground_range_mm = request.ground_range_mm
            state.bearing_deg = request.bearing_deg
            state.sequence = request.sequence
            state.updated_at = current
            state.last_heartbeat_at = current
            state.pending = True
            response = _response(state)
        self._publish(response)
        return response

    def heartbeat(self, site_id: str, request: WaterGunHeartbeatRequest) -> WaterGunStateResponse:
        with self._lock:
            state = self._state(site_id)
            if state.mode != "dynamic" or state.session_id != request.session_id:
                raise LookupError("动态控制会话不存在或已经结束。")
            previous = replace(state)
            state.last_heartbeat_at = _now_ms()
            return _response(state)

    def stop_dynamic(self, db: Session, site_id: str, request: WaterGunStopRequest) -> WaterGunStateResponse:
        current = _now_ms()
        with self._lock:
            state = self._state(site_id)
            if state.mode != "dynamic" or state.session_id != request.session_id:
                raise LookupError("动态控制会话不存在或已经结束。")
            state.mode = "static"
            state.spray_enabled = request.keep_spraying
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

    def _queue_state(self, db: Session, state: _WaterGunState, reason: str) -> int:
        water_gun = {
            "mode": state.mode,
            "spray_enabled": state.spray_enabled,
            "simulation_only": _simulation_only(),
            "pump_control_percent": round(_pump_control_percent(state), 1),
            "session_id": state.session_id,
            "sequence": state.sequence,
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
            with self._lock:
                for site_id, state in self._states.items():
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
                            state.last_command_id = self._queue_state(db, state, "动态会话超时，自动停止水泵")
                            response = _response(state)
                        self._publish(response)
                except Exception:
                    logger.exception("Unable to queue water-gun timeout stop for %s", site_id)


water_gun_runtime = WaterGunRuntime()
