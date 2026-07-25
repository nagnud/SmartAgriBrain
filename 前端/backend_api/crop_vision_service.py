from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app_state_service import read_app_state_value, save_app_state_value
from position_service import PixelDetection, project_to_ground
from schemas import CameraPositionConfig, CropPositionInfo, CurrentCropPositionsResponse
from vision_service import (
    MAX_VISION_IMAGE_BYTES,
    ALLOWED_IMAGE_MIME_TYPES,
    parse_json_object,
    safe_text,
    sanitize_bbox,
    sanitize_severity,
    clamp_number,
    vision_api_key,
    vision_chat_completion_url,
    vision_model,
    vision_timeout_seconds,
)


CURRENT_CROP_POSITIONS_KEY = "current-crop-positions"
MIN_CROP_CONFIDENCE = 0.2


def now_ms() -> int:
    return int(time.time() * 1000)


def build_crop_detection_prompt() -> str:
    return (
        "你是农业摄像头作物识别模块。请只识别画面中的作物本体或作物植株，非作物、工具、管线、盆、标签、人体、墙面等不要输出。"
        "如果画面没有作物，返回 {\"crops\":[]}。"
        "每个作物实例都要返回 bbox 和 anchor；bbox 使用整张图的百分比左上角 x/y/width/height，anchor 是用于水枪瞄准的百分比点。"
        "低矮或铺展作物 anchor 取可喷淋区域中心；直立植株优先取底部附近的冠层投影中心。"
        "clear_enough 表示画面是否足够清晰到可以判断生长状况与病虫害。"
        "只有 clear_enough=true 时才填写具体 growth_status、pest_disease_status 和 summary；不清晰时这些字段写“画面不够清晰，暂不判断”。"
        "病虫害和生长状态只基于图像证据，不要臆测。severity 只能是 healthy、low、medium、high。"
        "只输出合法 JSON，格式："
        "{\"crops\":[{\"label\":\"作物名称\",\"crop_name\":\"作物名称\",\"confidence\":0到1,"
        "\"bbox\":{\"x\":0到100,\"y\":0到100,\"width\":0到100,\"height\":0到100},"
        "\"anchor\":{\"x\":0到100,\"y\":0到100},\"clear_enough\":true或false,"
        "\"growth_status\":\"生长状况\",\"pest_disease_status\":\"病虫害判断\","
        "\"severity\":\"healthy|low|medium|high\",\"summary\":\"一句话说明\"}]}"
    )


def _call_crop_detector(image_bytes: bytes, content_type: str) -> dict[str, Any]:
    if not image_bytes:
        raise HTTPException(status_code=400, detail="作物识别图片为空。")
    if len(image_bytes) > MAX_VISION_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="作物识别图片超过大小限制。")
    if content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(status_code=400, detail="仅支持 jpg、png 或 webp 图像。")
    api_key = vision_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="VISION_API_KEY is not configured.")

    body = {
        "model": vision_model(),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": build_crop_detection_prompt()},
            {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('ascii')}" }},
        ]}],
        "temperature": 0.0,
        "max_tokens": 1400,
        "response_format": {"type": "json_object"},
    }
    try:
        with httpx.Client(timeout=vision_timeout_seconds()) as client:
            response = client.post(
                vision_chat_completion_url(),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
        result = response.json()
        choices = result.get("choices") if isinstance(result, dict) else None
        message = choices[0].get("message") if isinstance(choices, list) and choices else None
        content = message.get("content") if isinstance(message, dict) else None
        if content is None:
            raise ValueError("vision response missing content")
        return parse_json_object(str(content))
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=502, detail=f"作物识别服务暂时不可用：{error}") from error


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "清晰", "是"}
    return bool(value)


def _anchor_from_crop(item: dict[str, Any], bbox: dict[str, float]) -> tuple[float, float]:
    raw_anchor = item.get("anchor") if isinstance(item.get("anchor"), dict) else {}
    fallback_x = bbox["x"] + bbox["width"] / 2
    fallback_y = bbox["y"] + bbox["height"] / 2
    try:
        x = float(raw_anchor.get("x", fallback_x))
        y = float(raw_anchor.get("y", fallback_y))
    except (TypeError, ValueError):
        return fallback_x, fallback_y
    min_x, max_x = bbox["x"], bbox["x"] + bbox["width"]
    min_y, max_y = bbox["y"], bbox["y"] + bbox["height"]
    if not (min_x <= x <= max_x and min_y <= y <= max_y):
        return fallback_x, fallback_y
    return min(100.0, max(0.0, x)), min(100.0, max(0.0, y))


def _crop_items(raw_result: dict[str, Any]) -> list[dict[str, Any]]:
    raw_crops = raw_result.get("crops")
    if raw_crops is None:
        raw_crops = raw_result.get("detections")
    return raw_crops if isinstance(raw_crops, list) else []


def _normalize_crop(item: dict[str, Any], index: int, config: CameraPositionConfig) -> CropPositionInfo | None:
    label = safe_text(item.get("crop_name") or item.get("label") or item.get("name"))
    if not label:
        return None
    confidence = round(clamp_number(item.get("confidence"), 0, 1, 0), 3)
    if confidence < MIN_CROP_CONFIDENCE:
        return None
    bbox = sanitize_bbox(item.get("bbox"))
    if bbox["width"] <= 0 or bbox["height"] <= 0:
        return None
    anchor_x, anchor_y = _anchor_from_crop(item, bbox)
    clear_enough = _safe_bool(item.get("clear_enough"))
    unclear_text = "画面不够清晰，暂不判断。"
    growth_status = safe_text(item.get("growth_status"), unclear_text) if clear_enough else unclear_text
    pest_disease_status = safe_text(item.get("pest_disease_status"), unclear_text) if clear_enough else unclear_text
    summary = safe_text(item.get("summary"), f"识别到{label}。") if clear_enough else f"识别到{label}，但画面不够清晰，暂不判断长势和病虫害。"
    crop = CropPositionInfo(
        id=safe_text(item.get("id"), f"crop-{index + 1}-{uuid.uuid4().hex[:8]}")[:80],
        label=label[:80],
        crop_name=safe_text(item.get("crop_name"), label)[:80],
        confidence=confidence,
        bbox=bbox,
        anchor={"x": round(anchor_x, 2), "y": round(anchor_y, 2)},
        clear_enough=clear_enough,
        growth_status=growth_status[:180],
        pest_disease_status=pest_disease_status[:180],
        severity=sanitize_severity(item.get("severity") or item.get("risk_level")),
        summary=summary[:240],
    )
    if not config.calibrated:
        return crop

    detection = PixelDetection(
        crop.label,
        crop.confidence,
        bbox["x"],
        bbox["y"],
        bbox["width"],
        bbox["height"],
        description=crop.summary,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
        anchor_type="surface_center",
        estimated_height_mm=0,
        height_confidence=0,
        height_estimate_provided=False,
    )
    candidate = project_to_ground(detection, config)
    if candidate is None:
        crop.coordinate_status = "invalid_geometry"
        return crop
    crop.ground_range_mm = candidate.ground_range_mm
    crop.bearing_deg = candidate.bearing_deg
    crop.coordinate_status = "located"
    return crop


def detect_current_crop_positions(
    image_bytes: bytes,
    content_type: str,
    config: CameraPositionConfig,
    captured_at: int | None = None,
) -> CurrentCropPositionsResponse:
    raw_result = _call_crop_detector(image_bytes, content_type)
    crops = [
        crop
        for index, item in enumerate(_crop_items(raw_result))
        if isinstance(item, dict) and (crop := _normalize_crop(item, index, config)) is not None
    ][:12]
    status = "ok" if config.calibrated else "calibration_missing"
    message = "" if config.calibrated else "相机定位参数未标定，已识别作物但无法换算水枪坐标。"
    return CurrentCropPositionsResponse(
        status=status,
        message=message,
        captured_at=int(captured_at or now_ms()),
        crops=crops,
    )


def save_current_crop_positions(db: Session, result: CurrentCropPositionsResponse) -> CurrentCropPositionsResponse:
    save_app_state_value(db, CURRENT_CROP_POSITIONS_KEY, result.model_dump(mode="json"))
    return result


def read_current_crop_positions(db: Session) -> CurrentCropPositionsResponse:
    raw = read_app_state_value(db, CURRENT_CROP_POSITIONS_KEY)
    if not raw:
        return CurrentCropPositionsResponse(status="ok", captured_at=now_ms(), crops=[])
    try:
        return CurrentCropPositionsResponse.model_validate(raw)
    except Exception:
        return CurrentCropPositionsResponse(status="ok", captured_at=now_ms(), crops=[])
