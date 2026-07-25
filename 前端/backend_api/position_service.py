from __future__ import annotations

import base64
import json
import math
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException

from schemas import CameraPositionConfig, PositionCandidate, PositionLocateResponse
from position_capture_service import save_position_capture
from vision_service import (
    MAX_VISION_IMAGE_BYTES,
    parse_json_object,
    vision_api_key,
    vision_chat_completion_url,
    vision_model,
    vision_timeout_seconds,
)


POSITION_RESULT_TTL_MS = 5 * 60 * 1000
MIN_DETECTION_CONFIDENCE = 0.2
MIN_HEIGHT_CONFIDENCE = 0.55
ANCHOR_TYPES = {"visual_center", "surface_center", "footprint_center", "custom"}
_position_results: dict[str, tuple[int, PositionCandidate]] = {}


@dataclass(frozen=True)
class PixelDetection:
    label: str
    confidence: float
    x: float
    y: float
    width: float
    height: float
    description: str = ""
    attributes: dict[str, str] | None = None
    anchor_x: float | None = None
    anchor_y: float | None = None
    anchor_type: str = "visual_center"
    estimated_height_mm: float = 0.0
    height_confidence: float = 0.0
    anchor_reason: str = ""
    height_estimate_provided: bool = False


def now_ms() -> int:
    return int(time.time() * 1000)


def build_position_prompt(question: str) -> str:
    return (
        "你是支持多轮筛选的目标定位视觉模块。根据用户问题，在图片中寻找被询问的物体；不要分析病虫害。"
        "如果用户说“水果”“果子”“果实”或询问画面里是什么水果，必须识别每个可见水果的具体种类，"
        "例如苹果、梨、香蕉、橙子、番茄等，label 必须写具体水果名，不要只写“水果”。"
        "当用户只泛称水果且画面里有多个水果时，返回所有可见水果候选；当用户点名某种水果时，只返回该具体水果。"
        "用户可能是在上一轮多个同类候选中继续筛选。此时必须逐个比较颜色、材质、形状、大小、文字、配件和相对位置等描述，"
        "只返回真正符合本轮描述的候选，不得因为物体类别相同就把全部同类物体再次返回。"
        "如果描述是‘银色的’‘带盖子的’‘较长的’等而没有重复物体名称，应结合问题中的上一轮目标类别理解。"
        "只输出合法 JSON，格式为："
        '{"detections":[{"label":"中文物体名称","confidence":0到1,'
        '"description":"颜色、材质、形状、文字和配件等显著特征",'
        '"attributes":{"color":"颜色","material":"材质","shape":"形状","text":"可见文字"},'
        '"bbox":{"x":0到100,"y":0到100,"width":0到100,"height":0到100},'
        '"anchor":{"x":0到100,"y":0到100,"type":"visual_center|surface_center|footprint_center|custom",'
        '"height_mm":非负毫米数,"height_confidence":0到1,"reason":"简短选点与高度依据"}}]}。'
        "bbox 是相对整张图的百分比左上角和宽高。若没有目标则 detections 为 []。"
        "anchor.x/y 是相对整张图片的百分比定位点，必须落在目标框内。"
        "平放或低矮物体优先选真实轮廓中心；明显竖立物体的一般位置优先选底面中心；"
        "用户明确询问物体中心时可选物体中心并估计该点离桌面的高度。"
        "无法可靠判断高度时必须返回 height_mm=0、较低的 height_confidence，并在 reason 中说明按桌面投影。"
        "你只负责选择像素锚点和估计高度，不得计算距离、角度或坐标。"
        "符合用户本轮全部描述的目标仍有多个时，才把这些匹配目标全部返回，不要合并。"
        f"\n用户问题：{question[:500]}"
    )


def call_object_locator(image_bytes: bytes, content_type: str, question: str) -> dict[str, Any]:
    if not image_bytes:
        raise HTTPException(status_code=400, detail="定位图片为空。")
    if len(image_bytes) > MAX_VISION_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="定位图片超过大小限制。")
    api_key = vision_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="VISION_API_KEY is not configured.")

    body = {
        "model": vision_model(),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": build_position_prompt(question)},
            {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"}},
        ]}],
        "temperature": 0.0,
        "max_tokens": 1000,
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
        raise HTTPException(status_code=502, detail=f"目标识别服务暂时不可用：{error}") from error


def normalize_detections(raw: Any) -> list[PixelDetection]:
    if not isinstance(raw, list):
        return []
    detections: list[PixelDetection] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
        try:
            confidence = float(item.get("confidence", 0))
            x, y = float(bbox.get("x", 0)), float(bbox.get("y", 0))
            width, height = float(bbox.get("width", 0)), float(bbox.get("height", 0))
        except (TypeError, ValueError):
            continue
        label = str(item.get("label") or item.get("name") or "目标").strip()[:80]
        if not label or confidence < MIN_DETECTION_CONFIDENCE or width <= 0 or height <= 0:
            continue
        x = min(100.0, max(0.0, x))
        y = min(100.0, max(0.0, y))
        width = min(100.0 - x, max(0.0, width))
        height = min(100.0 - y, max(0.0, height))
        if width > 0 and height > 0:
            description = str(item.get("description") or "").strip()[:160]
            raw_attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            attributes = {
                str(key)[:32]: str(value).strip()[:80]
                for key, value in raw_attributes.items()
                if str(value).strip()
            }
            raw_anchor = item.get("anchor") if isinstance(item.get("anchor"), dict) else {}
            anchor_x: float | None = None
            anchor_y: float | None = None
            try:
                proposed_x = float(raw_anchor.get("x"))
                proposed_y = float(raw_anchor.get("y"))
                if x <= proposed_x <= x + width and y <= proposed_y <= y + height:
                    anchor_x = min(100.0, max(0.0, proposed_x))
                    anchor_y = min(100.0, max(0.0, proposed_y))
            except (TypeError, ValueError):
                pass
            anchor_type = str(raw_anchor.get("type") or "visual_center").strip().lower()
            if anchor_type not in ANCHOR_TYPES:
                anchor_type = "custom" if anchor_x is not None else "visual_center"
            height_estimate_provided = "height_mm" in raw_anchor and "height_confidence" in raw_anchor
            try:
                estimated_height_mm = min(10_000.0, max(0.0, float(raw_anchor.get("height_mm", 0))))
            except (TypeError, ValueError):
                estimated_height_mm = 0.0
                height_estimate_provided = False
            try:
                height_confidence = min(1.0, max(0.0, float(raw_anchor.get("height_confidence", 0))))
            except (TypeError, ValueError):
                height_confidence = 0.0
                height_estimate_provided = False
            anchor_reason = str(raw_anchor.get("reason") or "").strip()[:180]
            detections.append(
                PixelDetection(
                    label,
                    min(1.0, max(0.0, confidence)),
                    x,
                    y,
                    width,
                    height,
                    description,
                    attributes,
                    anchor_x,
                    anchor_y,
                    anchor_type,
                    estimated_height_mm,
                    height_confidence,
                    anchor_reason,
                    height_estimate_provided,
                )
            )
    return detections


def undistort_normalized(x_distorted: float, y_distorted: float, distortion: list[float]) -> tuple[float, float]:
    """Invert the common OpenCV k1, k2, p1, p2, k3 distortion model."""
    if not distortion:
        return x_distorted, y_distorted
    values = [*distortion, 0.0, 0.0, 0.0, 0.0, 0.0]
    k1, k2, p1, p2, k3 = values[:5]
    x, y = x_distorted, y_distorted
    for _ in range(8):
        radius2 = x * x + y * y
        radial = 1 + k1 * radius2 + k2 * radius2 * radius2 + k3 * radius2 * radius2 * radius2
        estimate_x = x * radial + 2 * p1 * x * y + p2 * (radius2 + 2 * x * x)
        estimate_y = y * radial + p1 * (radius2 + 2 * y * y) + 2 * p2 * x * y
        x += x_distorted - estimate_x
        y += y_distorted - estimate_y
    return x, y


def project_to_ground(detection: PixelDetection, config: CameraPositionConfig) -> PositionCandidate | None:
    """Intersect the AI-selected pixel ray with its validated height plane.

    World axes are forward, right, up. The origin is the lens's vertical ground projection,
    therefore the returned bearing is positive to the right from the configured forward axis.
    """
    anchor_x = detection.anchor_x if detection.anchor_x is not None else detection.x + detection.width / 2
    anchor_y = detection.anchor_y if detection.anchor_y is not None else detection.y + detection.height / 2
    u = anchor_x / 100 * config.image_width
    v = anchor_y / 100 * config.image_height
    x_cam, y_cam = undistort_normalized(
        (u - config.cx) / config.fx,
        (v - config.cy) / config.fy,
        config.distortion,
    )

    roll = math.radians(config.roll_deg)
    pitch = math.radians(config.pitch_down_deg)
    yaw = math.radians(config.yaw_deg)
    x_roll = math.cos(roll) * x_cam - math.sin(roll) * y_cam
    y_roll = math.sin(roll) * x_cam + math.cos(roll) * y_cam

    # The image Y axis points downward. After pitching the optical axis down,
    # the camera's image-down basis points partly backward in the ground plane,
    # so its forward component is negative. Using a plus sign here makes lower
    # pixels incorrectly appear farther away and cannot fit real ground points.
    forward = math.cos(pitch) - math.sin(pitch) * y_roll
    right = x_roll
    up = -math.sin(pitch) - math.cos(pitch) * y_roll
    if up >= -1e-6:
        return None
    height_is_valid = (
        detection.height_estimate_provided
        and detection.height_confidence >= MIN_HEIGHT_CONFIDENCE
        and detection.estimated_height_mm < config.camera_height_mm
    )
    effective_height_mm = detection.estimated_height_mm if height_is_valid else 0.0
    height_fallback = not height_is_valid
    scale = (config.camera_height_mm - effective_height_mm) / -up
    local_forward = scale * forward
    local_right = scale * right
    world_forward = math.cos(yaw) * local_forward - math.sin(yaw) * local_right
    world_right = math.sin(yaw) * local_forward + math.cos(yaw) * local_right
    ground_range = math.hypot(world_forward, world_right)
    vertical_distance = config.camera_height_mm - effective_height_mm
    camera_range = math.sqrt(ground_range * ground_range + vertical_distance * vertical_distance)
    bearing = math.degrees(math.atan2(world_right, world_forward))
    return PositionCandidate(
        id=f"candidate-{uuid.uuid4().hex[:12]}",
        label=detection.label,
        confidence=round(detection.confidence, 3),
        bbox={"x": round(detection.x, 2), "y": round(detection.y, 2), "width": round(detection.width, 2), "height": round(detection.height, 2)},
        camera_range_mm=round(camera_range, 1),
        ground_range_mm=round(ground_range, 1),
        bearing_deg=round(bearing, 1),
        description=detection.description,
        attributes=detection.attributes or {},
        anchor={"x": round(anchor_x, 2), "y": round(anchor_y, 2)},
        anchor_type=detection.anchor_type if detection.anchor_x is not None else "visual_center",
        estimated_height_mm=round(detection.estimated_height_mm, 1),
        effective_height_mm=round(effective_height_mm, 1),
        height_confidence=round(detection.height_confidence, 3),
        height_fallback=height_fallback,
        anchor_reason=(
            "AI 未可靠判断高度，已按桌面高度 0 mm 计算。"
            if height_fallback
            else detection.anchor_reason or "AI 已选择定位点并估计其高度。"
        ),
    )


def _remember(candidate: PositionCandidate) -> str:
    timestamp = now_ms()
    for result_id, (created_at, _) in list(_position_results.items()):
        if created_at + POSITION_RESULT_TTL_MS < timestamp:
            _position_results.pop(result_id, None)
    result_id = f"position-{uuid.uuid4().hex}"
    _position_results[result_id] = (timestamp, candidate)
    return result_id


def take_position_result(result_id: str) -> tuple[PositionCandidate, int] | None:
    item = _position_results.get(result_id)
    if item is None or item[0] + POSITION_RESULT_TTL_MS < now_ms():
        _position_results.pop(result_id, None)
        return None
    return item[1], item[0]


GENERIC_FRUIT_TERMS = ("水果", "果子", "果实", "fruit", "fruits")


def _label_matches_question(label: str, question: str) -> bool:
    normalized_question = question.replace(" ", "").lower()
    normalized_label = label.replace(" ", "").lower()
    if not normalized_label:
        return False
    if any(term in normalized_question for term in GENERIC_FRUIT_TERMS):
        return False
    return normalized_label in normalized_question


def _candidate_label_summary(candidates: list[PositionCandidate]) -> str:
    labels = list(dict.fromkeys(candidate.label for candidate in candidates if candidate.label.strip()))
    if not labels:
        return "多个目标"
    return "、".join(labels[:6])


def select_candidate_by_question(candidates: list[PositionCandidate], question: str) -> PositionCandidate | None:
    normalized = question.replace(" ", "").lower()
    label_matches = [candidate for candidate in candidates if _label_matches_question(candidate.label, normalized)]
    if len(label_matches) == 1:
        return label_matches[0]
    if "左" in normalized or "left" in normalized:
        return min(candidates, key=lambda item: item.bbox["x"] + item.bbox["width"] / 2)
    if "右" in normalized or "right" in normalized:
        return max(candidates, key=lambda item: item.bbox["x"] + item.bbox["width"] / 2)
    if "最近" in normalized or "nearest" in normalized:
        return min(candidates, key=lambda item: item.camera_range_mm)
    return None


def locate_from_vision_result(
    question: str,
    raw_result: dict[str, Any],
    config: CameraPositionConfig,
    captured_at: int | None = None,
) -> PositionLocateResponse:
    captured_at = int(captured_at or now_ms())
    if not config.calibrated:
        return PositionLocateResponse(status="calibration_missing", message="请先在相机定位参数中填写并保存 fx、fy、cx、cy 标定值。", captured_at=captured_at)
    candidates = [candidate for detection in normalize_detections(raw_result.get("detections")) if (candidate := project_to_ground(detection, config)) is not None]
    if not candidates:
        raw_detections = normalize_detections(raw_result.get("detections"))
        status = "invalid_geometry" if raw_detections else "not_found"
        message = "目标位于镜头可计算范围外，请调整镜头俯角后重试。" if raw_detections else "当前画面未找到你询问的目标，请调整物体位置或换一种描述。"
        return PositionLocateResponse(status=status, message=message, captured_at=captured_at)
    if len(candidates) > 1:
        selected = select_candidate_by_question(candidates, question)
        if selected is not None:
            return PositionLocateResponse(
                status="located",
                result_id=_remember(selected),
                message="已按你的描述选择目标并定位成功。",
                captured_at=captured_at,
                candidates=candidates,
                selected=selected,
            )
        return PositionLocateResponse(
            status="multiple",
            message=f"发现多个目标：{_candidate_label_summary(candidates)}。请说明要操作哪一个，也可以继续描述颜色、大小、左边、右边或最近的一个。",
            captured_at=captured_at,
            candidates=candidates,
        )
    candidate = candidates[0]
    result_id = _remember(candidate)
    return PositionLocateResponse(status="located", result_id=result_id, message="定位成功。", captured_at=captured_at, candidates=[candidate], selected=candidate)


def locate_object(
    image_bytes: bytes,
    content_type: str,
    question: str,
    config: CameraPositionConfig,
    captured_at: int | None = None,
) -> PositionLocateResponse:
    raw_result = call_object_locator(image_bytes, content_type, question)
    actual_captured_at = int(captured_at or now_ms())
    result = locate_from_vision_result(question, raw_result, config, actual_captured_at)
    image_url, width, height = save_position_capture(image_bytes, result, actual_captured_at)
    result.annotated_image_url = image_url
    result.image_width = width
    result.image_height = height
    return result
