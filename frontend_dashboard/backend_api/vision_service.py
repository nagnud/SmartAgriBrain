from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Dict, List, Literal

import httpx
from fastapi import HTTPException, UploadFile

from deepseek_service import call_deepseek_chat, deepseek_api_key, strip_code_fence


DEFAULT_VISION_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_VISION_MODEL = "doubao-seed-2-0-mini-260428"
MAX_VISION_IMAGE_BYTES = int(os.getenv("VISION_IMAGE_MAX_BYTES", str(10 * 1024 * 1024)))
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
Severity = Literal["healthy", "low", "medium", "high"]


def is_placeholder_secret(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or lowered.startswith("your_") or lowered in {"your-api-key", "your-vision-api-key"}


def vision_api_key() -> str:
    value = os.getenv("VISION_API_KEY", "").strip()
    return "" if is_placeholder_secret(value) else value


def vision_model() -> str:
    return os.getenv("VISION_MODEL", DEFAULT_VISION_MODEL).strip() or DEFAULT_VISION_MODEL


def vision_chat_completion_url() -> str:
    base_url = os.getenv("VISION_BASE_URL", DEFAULT_VISION_BASE_URL).strip() or DEFAULT_VISION_BASE_URL
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def vision_timeout_seconds(default: float = 90.0) -> float:
    raw = os.getenv("VISION_TIMEOUT_SECONDS", str(default)).strip()
    try:
        return max(float(raw), 1.0)
    except ValueError:
        return default


def normalized_content_type(upload: UploadFile) -> str:
    return (upload.content_type or "").split(";", 1)[0].strip().lower()


def parse_json_object(content: str) -> Dict[str, Any]:
    parsed = json.loads(strip_code_fence(content))
    if not isinstance(parsed, dict):
        raise ValueError("AI response must be a JSON object")
    return parsed


def safe_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def clamp_number(value: Any, minimum: float, maximum: float, fallback: float) -> float:
    return max(minimum, min(maximum, safe_float(value, fallback)))


def sanitize_severity(value: Any) -> Severity:
    text = safe_text(value).lower()
    if text in {"healthy", "low", "medium", "high"}:
        return text  # type: ignore[return-value]
    if text in {"none", "normal", "good", "stable", "健康", "正常", "稳定"}:
        return "healthy"
    if text in {"mild", "轻微", "轻度"}:
        return "low"
    if text in {"moderate", "中等", "中度"}:
        return "medium"
    if text in {"severe", "danger", "严重", "高风险"}:
        return "high"
    return "low"


def sanitize_bbox(value: Any) -> Dict[str, float]:
    if not isinstance(value, dict):
        return {"x": 0, "y": 0, "width": 0, "height": 0}
    x = clamp_number(value.get("x"), 0, 100, 0)
    y = clamp_number(value.get("y"), 0, 100, 0)
    width = clamp_number(value.get("width"), 0, 100 - x, 0)
    height = clamp_number(value.get("height"), 0, 100 - y, 0)
    return {"x": round(x, 2), "y": round(y, 2), "width": round(width, 2), "height": round(height, 2)}


def sanitize_detections(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    detections: List[Dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        label = safe_text(item.get("label") or item.get("name") or item.get("disease") or item.get("issue"))
        if not label:
            continue
        bbox = sanitize_bbox(item.get("bbox"))
        has_box = bbox["width"] > 0 and bbox["height"] > 0
        detections.append(
            {
                "id": safe_text(item.get("id"), f"det-{index + 1}")[:60],
                "label": label[:80],
                "class_name": safe_text(item.get("class_name") or item.get("class") or item.get("type"), "visual_observation")[:80],
                "confidence": round(clamp_number(item.get("confidence"), 0, 1, 0), 3),
                "bbox": bbox if has_box else {"x": 0, "y": 0, "width": 0, "height": 0},
                "severity": sanitize_severity(item.get("severity") or item.get("risk_level")),
            }
        )
        if len(detections) >= 6:
            break
    return detections


def clamp_text_list(value: Any, limit: int) -> List[str]:
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        return []

    items: List[str] = []
    for item in raw_items:
        text = safe_text(item)
        if not text:
            continue
        items.append(text[:160])
        if len(items) >= limit:
            break
    return items


def build_ark_prompt() -> str:
    return (
        "你是农业图像识别助手。请分析这张作物图片中的病虫害风险和作物生长状况，只输出合法 JSON。"
        "如果画面中存在可见的病斑、虫害、霉层、枯黄、坏死、卷叶等异常区域，detections 必须尽量返回对应的 bbox。"
        "bbox 使用百分比坐标：x/y 是异常区域左上角相对整张图片的百分比，width/height 是区域宽高百分比。"
        "如果画面里没有作物、没有可见异常，或无法可靠定位异常区域，detections 返回空数组，不要乱画框。"
        "输出格式："
        "{\"crop\":\"作物名称或unknown\",\"growth_status\":\"生长状况\","
        "\"pest_disease_status\":\"病虫害状况\","
        "\"detections\":[{\"label\":\"疑似问题\",\"class_name\":\"英文或拼音类别\","
        "\"confidence\":0到1,\"bbox\":{\"x\":百分比,\"y\":百分比,\"width\":百分比,\"height\":百分比},"
        "\"severity\":\"healthy|low|medium|high\"}],"
        "\"observations\":[\"图像证据\"],\"risk_level\":\"healthy|low|medium|high\"}"
    )


def call_ark_vision(image_bytes: bytes, content_type: str) -> Dict[str, Any]:
    api_key = vision_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="VISION_API_KEY is not configured.")

    image_base64 = base64.b64encode(image_bytes).decode("ascii")
    body = {
        "model": vision_model(),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_ark_prompt()},
                    {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{image_base64}"}},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=vision_timeout_seconds()) as client:
            try:
                response = client.post(vision_chat_completion_url(), headers=headers, json=body)
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                if error.response.status_code not in {400, 422}:
                    raise
                retry_body = dict(body)
                retry_body.pop("response_format", None)
                response = client.post(vision_chat_completion_url(), headers=headers, json=retry_body)
                response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as error:
        detail = error.response.text[:600] if error.response is not None else str(error)
        friendly_detail = format_ark_error_detail(detail)
        if friendly_detail:
            raise HTTPException(status_code=502, detail=friendly_detail) from error
        raise HTTPException(status_code=502, detail=f"Vision API request failed: {detail}") from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Vision API is unavailable: {error}") from error

    choices = result.get("choices")
    content = None
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
    if content is None:
        raise HTTPException(status_code=502, detail="Vision API response missing message content.")

    try:
        return parse_json_object(str(content))
    except (json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=502, detail=f"Vision API returned invalid JSON: {error}") from error


def format_ark_error_detail(raw_detail: str) -> str:
    try:
        parsed = json.loads(raw_detail)
    except json.JSONDecodeError:
        return ""

    error = parsed.get("error") if isinstance(parsed, dict) else None
    if not isinstance(error, dict):
        return ""

    code = safe_text(error.get("code"))
    message = safe_text(error.get("message"))
    if code == "ModelNotOpen":
        return (
            f"火山方舟模型未开通：当前账号还没有开通 {vision_model()}。"
            "请在火山方舟控制台的“开通管理”里开通该模型，或把 backend_api/.env 里的 VISION_MODEL 改成已开通的模型。"
            f" 原始信息：{message}"
        )
    if code:
        return f"火山方舟视觉接口返回错误：{code}。{message}"
    return ""


def build_deepseek_prompt(vision_result: Dict[str, Any]) -> str:
    return (
        "你是智慧农业系统的自然语言分析助手。下面是火山方舟视觉模型对作物图片的结构化识别结果。"
        "请严格基于该结果输出中文 JSON，不要增加视觉结果里没有依据的病害结论。"
        "输出格式：{\"summary\":\"一句话概括生长和病虫害状况\","
        "\"explanation\":\"结合图像证据说明原因\","
        "\"suggestions\":[\"建议1\",\"建议2\",\"建议3\"]}。"
        f"\n火山方舟识别结果：{json.dumps(vision_result, ensure_ascii=False)}"
    )


def call_deepseek_vision_summary(vision_result: Dict[str, Any]) -> Dict[str, Any]:
    if not deepseek_api_key():
        raise HTTPException(status_code=503, detail="DEEPSEEK_API_KEY is not configured.")
    try:
        content = call_deepseek_chat(
            [
                {
                    "role": "system",
                    "content": "你是专业农业图像分析师，只输出合法 JSON。",
                },
                {
                    "role": "user",
                    "content": build_deepseek_prompt(vision_result),
                },
            ],
            max_tokens=700,
            timeout_seconds=90,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return parse_json_object(content)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"DeepSeek vision summary failed: {error}") from error


async def analyze_disease_image(upload: UploadFile) -> Dict[str, Any]:
    content_type = normalized_content_type(upload)
    if content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Only jpg, png, and webp images are supported.")

    image_bytes = await upload.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    if len(image_bytes) > MAX_VISION_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded image exceeds the configured size limit.")

    vision_result = call_ark_vision(image_bytes, content_type)
    deepseek_result = call_deepseek_vision_summary(vision_result)

    return {
        "image_url": "",
        "crop": safe_text(vision_result.get("crop"), "unknown")[:60],
        "model": vision_model(),
        "detections": sanitize_detections(vision_result.get("detections")),
        "summary": safe_text(deepseek_result.get("summary"), "图像识别已完成，但未生成摘要。")[:180],
        "explanation": safe_text(deepseek_result.get("explanation"), "DeepSeek 未返回详细解释。")[:500],
        "suggestions": clamp_text_list(deepseek_result.get("suggestions"), 5),
        "processed_at": int(time.time() * 1000),
        "vision_observations": clamp_text_list(vision_result.get("observations"), 8),
        "growth_status": safe_text(vision_result.get("growth_status"), ""),
        "pest_disease_status": safe_text(vision_result.get("pest_disease_status"), ""),
    }
