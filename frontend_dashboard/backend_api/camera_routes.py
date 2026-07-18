from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app_state_service import read_app_state_value, save_app_state_value
from camera_service import camera_service
from database import get_db


router = APIRouter(prefix="/api/v1/camera", tags=["camera"])


class CameraConfig(BaseModel):
    device_index: int = Field(default=0, ge=0, le=20)
    width: int = Field(default=1280, ge=160, le=7680)
    height: int = Field(default=720, ge=120, le=4320)
    fps: int = Field(default=15, ge=1, le=30)


def configured_camera(db: Session) -> CameraConfig:
    raw = read_app_state_value(db, "backend-camera")
    try:
        return CameraConfig.model_validate(raw)
    except Exception:
        return CameraConfig()


@router.get("/status")
def read_camera_status(db: Session = Depends(get_db)) -> dict[str, object]:
    config = configured_camera(db)
    status = camera_service.status()
    return {**status, "ready": bool(status.get("connected")), "config": config.model_dump(mode="json")}


@router.put("/config")
def update_camera_config(payload: CameraConfig, db: Session = Depends(get_db)) -> dict[str, object]:
    save_app_state_value(db, "backend-camera", payload.model_dump(mode="json"))
    camera_service.configure(payload.device_index, payload.width, payload.height, payload.fps)
    return {"success": True, "config": payload.model_dump(mode="json")}


@router.get("/frame.jpg")
def read_camera_frame() -> Response:
    try:
        snapshot = camera_service.snapshot()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return Response(
        content=snapshot.jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "X-Captured-At": str(snapshot.captured_at)},
    )


@router.get("/stream.mjpg")
def stream_camera() -> StreamingResponse:
    return StreamingResponse(
        camera_service.mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
    )
