from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from water_gun_service import (
    WaterGunDynamicStartRequest,
    WaterGunDynamicSprayRequest,
    WaterGunDynamicUpdateRequest,
    WaterGunHeartbeatRequest,
    WaterGunPreviewRequest,
    WaterGunStateResponse,
    WaterGunStaticRequest,
    WaterGunStopRequest,
    water_gun_runtime,
)


router = APIRouter(prefix="/api/v1/sites", tags=["water-gun"])


@router.get("/{site_id}/water-gun", response_model=WaterGunStateResponse)
def read_water_gun(site_id: str) -> WaterGunStateResponse:
    return water_gun_runtime.read(site_id)


@router.post("/{site_id}/water-gun/preview", response_model=WaterGunStateResponse)
def preview_water_gun(site_id: str, payload: WaterGunPreviewRequest) -> WaterGunStateResponse:
    try:
        return water_gun_runtime.set_preview(site_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{site_id}/water-gun/static", response_model=WaterGunStateResponse)
def set_static_water_gun(
    site_id: str,
    payload: WaterGunStaticRequest,
    db: Session = Depends(get_db),
) -> WaterGunStateResponse:
    try:
        return water_gun_runtime.set_static(db, site_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=409, detail="水枪目标未进入设备队列，请检查 ESP32 设备状态。") from error


@router.post("/{site_id}/water-gun/dynamic/start", response_model=WaterGunStateResponse)
def start_dynamic_water_gun(
    site_id: str,
    payload: WaterGunDynamicStartRequest,
    db: Session = Depends(get_db),
) -> WaterGunStateResponse:
    try:
        return water_gun_runtime.start_dynamic(db, site_id, payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=409, detail="动态模式未能启动，请检查 ESP32 设备状态。") from error


@router.put("/{site_id}/water-gun/dynamic/target", response_model=WaterGunStateResponse)
def update_dynamic_water_gun(
    site_id: str,
    payload: WaterGunDynamicUpdateRequest,
) -> WaterGunStateResponse:
    try:
        return water_gun_runtime.update_dynamic(site_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/{site_id}/water-gun/dynamic/heartbeat", response_model=WaterGunStateResponse)
def heartbeat_dynamic_water_gun(
    site_id: str,
    payload: WaterGunHeartbeatRequest,
    db: Session = Depends(get_db),
) -> WaterGunStateResponse:
    try:
        return water_gun_runtime.heartbeat(db, site_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{site_id}/water-gun/dynamic/spray", response_model=WaterGunStateResponse)
def set_dynamic_water_gun_spray(
    site_id: str,
    payload: WaterGunDynamicSprayRequest,
    db: Session = Depends(get_db),
) -> WaterGunStateResponse:
    try:
        return water_gun_runtime.set_dynamic_spray(db, site_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=409, detail="动态水枪开关指令未进入设备队列，请立即检查设备状态。") from error


@router.post("/{site_id}/water-gun/dynamic/stop", response_model=WaterGunStateResponse)
def stop_dynamic_water_gun(
    site_id: str,
    payload: WaterGunStopRequest,
    db: Session = Depends(get_db),
) -> WaterGunStateResponse:
    try:
        return water_gun_runtime.stop_dynamic(db, site_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=409, detail="停止指令未进入设备队列，请立即检查设备状态。") from error
