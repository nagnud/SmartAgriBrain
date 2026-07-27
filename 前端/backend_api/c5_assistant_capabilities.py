from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app_state_service import read_app_state_value, save_app_state_value
from monitoring_models import AlarmRecord
from schemas import AssistantAction
from site_models import EdgeAssistantMessage, EdgeDeviceRecord
from site_schemas import GROW_LIGHT_MAX_PERCENT, GROW_LIGHT_MIN_PERCENT


logger = logging.getLogger(__name__)

C5_PARAMETER_TTL_MS = 5 * 60_000


def _danger_notice_key(site_id: str) -> str:
    return f"c5-danger-notices:{site_id}"


def pending_c5_danger_notice(db: Session, site_id: str) -> tuple[str, str] | None:
    """Return one unannounced open danger alarm. Failures never block the main answer."""

    try:
        device_ids = {
            row.device_id
            for row in db.query(EdgeDeviceRecord).filter(EdgeDeviceRecord.site_id == site_id).all()
        }
        query = db.query(AlarmRecord).filter(AlarmRecord.level == "danger", AlarmRecord.state == "open")
        if device_ids:
            query = query.filter(AlarmRecord.device_id.in_(device_ids))
        open_alarms = query.order_by(AlarmRecord.opened_at.asc()).limit(50).all()
        state = read_app_state_value(db, _danger_notice_key(site_id))
        announced = {str(item) for item in state.get("announced_alarm_ids", [])}
        alarm = next((item for item in open_alarms if item.id not in announced), None)
        if alarm is None:
            return None
        detail = re.sub(r"\s+", " ", str(alarm.detail or "")).strip()
        text = f"严重报警：{alarm.title}"
        if detail:
            text += f"，{detail[:28]}"
        return alarm.id, text.rstrip("。") + "。"
    except Exception:
        logger.exception("C5 danger notice lookup failed; continuing the user's turn")
        return None


def mark_c5_danger_notice(db: Session, site_id: str, alarm_id: str) -> None:
    try:
        state = read_app_state_value(db, _danger_notice_key(site_id))
        announced = [str(item) for item in state.get("announced_alarm_ids", [])]
        if alarm_id not in announced:
            announced.append(alarm_id)
        save_app_state_value(db, _danger_notice_key(site_id), {
            "announced_alarm_ids": announced[-200:],
        })
        logger.info("C5 assistant stage=danger_notice_marked alarm_id=%s", alarm_id)
    except Exception:
        logger.exception("C5 danger notice persistence failed; continuing the user's turn")


@dataclass(frozen=True)
class C5Capability:
    key: str
    label: str
    target: str
    command_prefix: str
    markers: tuple[str, ...]
    smart_key: str | None = None
    accepts_percentage: bool = True
    minimum_percent: int = GROW_LIGHT_MIN_PERCENT
    maximum_percent: int = GROW_LIGHT_MAX_PERCENT


@dataclass(frozen=True)
class C5ControlReply:
    answer: str
    context: dict[str, Any]
    actions: list[AssistantAction]


# The current ordinary ESP32 exposes only the grow light as a generic actuator.
# Water-gun positioning and spray operations use their dedicated contract.
C5_CAPABILITIES: tuple[C5Capability, ...] = (
    C5Capability("grow_light", "补光灯", "grow_light", "light", ("补光灯", "补光", "生长灯"), "light"),
)

_WATER_GUN_CAPABILITY = C5Capability(
    "water_gun", "水枪", "water_gun", "water_gun", ("水枪",), accepts_percentage=False
)

_CAPABILITY_BY_KEY = {item.key: item for item in C5_CAPABILITIES}
_CANCEL_MARKERS = ("取消", "算了", "不用了", "不要调", "停止设置")
_AUTO_MARKERS = ("自动模式", "恢复自动", "改成自动", "设为自动", "自动调节", "自动控制", "托管")
_ADJUST_MARKERS = ("调到", "调整到", "设置为", "设成", "调节", "调整", "设置", "改到", "改成")
_ON_MARKERS = ("打开", "开启", "启动", "浇一下水", "浇水", "加水", "灌一下水", "灌溉")
_OFF_MARKERS = ("关闭", "关掉", "停止", "停用")


def _compact(text: str) -> str:
    return "".join(str(text or "").lower().split()).strip("。！!？?")


def _chinese_integer(text: str) -> int | None:
    if not text or any(char not in "零〇一二两三四五六七八九十百" for char in text):
        return None
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
    if text == "百":
        return 100
    if "百" in text:
        before, after = text.split("百", 1)
        hundreds = digits.get(before, 1) * 100
        tail = _chinese_integer(after) if after else 0
        return hundreds + tail if tail is not None else None
    if "十" in text:
        before, after = text.split("十", 1)
        tens = digits.get(before, 1) * 10
        ones = digits.get(after, 0) if after else 0
        return tens + ones
    if len(text) == 1:
        return digits.get(text)
    if all(char in digits for char in text):
        return int("".join(str(digits[char]) for char in text))
    return None


def parse_c5_percentage(
    text: str,
    *,
    allow_bare: bool = False,
    minimum: int = GROW_LIGHT_MIN_PERCENT,
    maximum: int = GROW_LIGHT_MAX_PERCENT,
) -> int | None:
    """Parse one spoken brightness value within the physical output range.

    ``text`` is the ASR result. ``allow_bare`` is enabled only while answering
    an active parameter question, so an unrelated number is not interpreted as
    brightness. ``minimum`` and ``maximum`` must match the selected device
    capability and the ordinary ESP32 firmware.
    """

    compact = _compact(text)
    patterns = (
        r"百分之(\d{1,3})",
        r"(\d{1,3})(?:%|％)",
        r"(?:调到|设置为|设成|调整到|改到)(\d{1,3})(?:档)?",
    )
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            value = int(match.group(1))
            return value if minimum <= value <= maximum else None
    chinese = re.search(r"百分之([零〇一二两三四五六七八九十百]+)", compact)
    if chinese:
        value = _chinese_integer(chinese.group(1))
        return value if value is not None and minimum <= value <= maximum else None
    if allow_bare:
        bare = re.fullmatch(r"(\d{1,3})(?:档)?", compact)
        if bare:
            value = int(bare.group(1))
            return value if minimum <= value <= maximum else None
        value = _chinese_integer(compact)
        return value if value is not None and minimum <= value <= maximum else None
    return None


def _matched_capability(text: str) -> C5Capability | None:
    compact = _compact(text)
    # Longer, more specific names win (for example 二氧化碳阀 before generic 阀).
    matches = [item for item in C5_CAPABILITIES if any(marker in compact for marker in item.markers)]
    return max(matches, key=lambda item: max(len(marker) for marker in item.markers)) if matches else None


def _declared_actuators(raw: dict[str, Any]) -> tuple[set[str], bool]:
    aliases = {
        "light": "grow_light", "growlight": "grow_light", "grow_light": "grow_light",
        "co2": "co2_valve", "co2valve": "co2_valve", "co2_valve": "co2_valve",
        "vent": "ventilation", "ventilation": "ventilation",
        "water_gun": "water_gun", "watergun": "water_gun",
    }
    declared: set[str] = set()
    found_catalogue = False
    actuators = raw.get("actuators")
    if isinstance(actuators, dict):
        found_catalogue = True
        for key, value in actuators.items():
            normalized = aliases.get(str(key).lower(), str(key).lower())
            supported = value is not False
            if isinstance(value, dict):
                supported = value.get("supported", value.get("available", True)) is not False
            if supported:
                declared.add(normalized)
    elif isinstance(actuators, list):
        found_catalogue = True
        for value in actuators:
            key = value.get("key") if isinstance(value, dict) else value
            if key:
                declared.add(aliases.get(str(key).lower(), str(key).lower()))
    positioning = raw.get("positioning")
    if isinstance(positioning, dict) and "water_gun_control_supported" in positioning:
        found_catalogue = True
        if positioning.get("water_gun_control_supported") is True:
            declared.add("water_gun")
    return declared, found_catalogue


def c5_capability_block_reason(db: Session, site_id: str, capability: C5Capability) -> str | None:
    rows = list(db.query(EdgeDeviceRecord).filter(EdgeDeviceRecord.site_id == site_id).all())
    s3_rows = [row for row in rows if row.role == "sensor_actuator"]
    if not s3_rows:
        # Compatibility mode for deployments that have not reported capabilities yet.
        return None
    row = max(s3_rows, key=lambda item: item.last_seen_at)
    if not row.online or row.last_seen_at < int(time.time() * 1000) - 30_000:
        return f"设备暂未连接，暂时不能控制{capability.label}。"
    status = row.status if isinstance(row.status, dict) else {}
    interlocks = status.get("interlocks")
    if isinstance(interlocks, dict) and bool(interlocks.get(capability.key) or interlocks.get("all")):
        return f"{capability.label}当前处于安全保护状态，暂时不能操作。"
    if isinstance(interlocks, list) and capability.key in {str(item) for item in interlocks}:
        return f"{capability.label}当前处于安全保护状态，暂时不能操作。"
    raw = row.capabilities if isinstance(row.capabilities, dict) else {}
    declared, has_catalogue = _declared_actuators(raw)
    if has_catalogue and capability.key not in declared:
        return f"当前设备暂不支持控制{capability.label}。"
    return None


def c5_water_gun_block_reason(db: Session, site_id: str) -> str | None:
    return c5_capability_block_reason(db, site_id, _WATER_GUN_CAPABILITY)


def _parameter_context(capability: C5Capability, now: int, request_id: str | None = None) -> dict[str, Any]:
    return {
        "request_id": request_id or f"c5-param-{uuid.uuid4().hex}",
        "kind": "percentage_or_auto",
        "capability_key": capability.key,
        "target": capability.target,
        "label": capability.label,
        "command_prefix": capability.command_prefix,
        "smart_key": capability.smart_key,
        "minimum": capability.minimum_percent,
        "maximum": capability.maximum_percent,
        "candidates": ["百分比"],
        "expires_at": now + C5_PARAMETER_TTL_MS,
    }


def _pending_parameter(messages: Iterable[EdgeAssistantMessage], now: int) -> dict[str, Any] | None:
    resolved: set[str] = set()
    for message in reversed(list(messages)):
        metadata = message.message_metadata if isinstance(message.message_metadata, dict) else {}
        context = metadata.get("assistant_context") if isinstance(metadata.get("assistant_context"), dict) else {}
        raw_resolved = context.get("c5_parameter_resolved_ids")
        if isinstance(raw_resolved, list):
            resolved.update(str(item) for item in raw_resolved)
        pending = context.get("c5_parameter_request")
        if not isinstance(pending, dict):
            continue
        request_id = str(pending.get("request_id") or "")
        if request_id in resolved:
            continue
        return pending
    return None


def _device_action(
    capability: C5Capability,
    value: int,
    operation: str,
    mode: str = "manual",
) -> AssistantAction:
    """Create the pending control action shown and spoken by the C5.

    ``value`` has already passed capability-range validation. ``operation`` is
    the exact action repeated to the user before confirmation. ``mode`` stays
    manual because automatic grow-light control is not implemented.
    """

    command = f"{capability.command_prefix}_{'on' if value > 0 else 'off'}"
    return AssistantAction(
        id=f"assistant-action-c5-{uuid.uuid4().hex}",
        type="device_command",
        title=f"确认{operation}",
        description=f"确认后将{operation}，并等待设备回执。",
        risk="high",
        payload={
            "command": command,
            "target": capability.target,
            "value": value,
            "mode": mode,
            "reason": f"C5 现场助手请求{operation}",
        },
    )


def _confirmation_reply(capability: C5Capability, action: AssistantAction, operation: str,
                        resolved_id: str | None = None) -> C5ControlReply:
    context: dict[str, Any] = {"c5_stage": "confirmation", "c5_capability": capability.key}
    if resolved_id:
        context["c5_parameter_resolved_ids"] = [resolved_id]
    logger.info("C5 assistant stage=confirmation capability=%s operation=%s", capability.key, operation)
    return C5ControlReply(
        answer=f"请确认：{operation}。请说确认或取消。",
        context=context,
        actions=[action],
    )


def c5_control_reply(
    db: Session,
    site_id: str,
    text: str,
    messages: Iterable[EdgeAssistantMessage],
    now: int,
) -> C5ControlReply | None:
    """Resolve only C5 field-control turns; Web assistant never calls this state machine."""

    compact = _compact(text)
    pending = _pending_parameter(messages, now)
    if pending is not None:
        capability = _CAPABILITY_BY_KEY.get(str(pending.get("capability_key") or ""))
        request_id = str(pending.get("request_id") or "")
        if capability is None:
            return None
        if int(pending.get("expires_at") or 0) < now:
            logger.info("C5 assistant stage=parameter_expired capability=%s", capability.key)
            return C5ControlReply(
                f"刚才的{capability.label}设置已超时，不会执行；请重新说完整控制要求。",
                {"c5_parameter_resolved_ids": [request_id], "c5_stage": "expired"},
                [],
            )
        if any(marker in compact for marker in _CANCEL_MARKERS):
            logger.info("C5 assistant stage=parameter_canceled capability=%s", capability.key)
            return C5ControlReply(
                f"已取消设置{capability.label}，不会生成命令。",
                {"c5_parameter_resolved_ids": [request_id], "c5_stage": "canceled"},
                [],
            )
        block_reason = c5_capability_block_reason(db, site_id, capability)
        if block_reason:
            logger.info("C5 assistant stage=capability_blocked capability=%s", capability.key)
            return C5ControlReply(
                block_reason,
                {"c5_parameter_resolved_ids": [request_id], "c5_stage": "blocked"},
                [],
            )
        if any(marker in compact for marker in _AUTO_MARKERS):
            return C5ControlReply(
                f"当前未配置补光灯自动控制策略，请直接提供 "
                f"{capability.minimum_percent} 到 {capability.maximum_percent} 的亮度百分比。",
                {"c5_parameter_resolved_ids": [request_id], "c5_stage": "unsupported_auto_mode"},
                [],
            )
        value = parse_c5_percentage(
            compact,
            allow_bare=True,
            minimum=capability.minimum_percent,
            maximum=capability.maximum_percent,
        )
        if value is not None:
            operation = f"把{capability.label}调到 {value}%"
            return _confirmation_reply(
                capability,
                _device_action(capability, value, operation),
                operation,
                request_id,
            )
        logger.info("C5 assistant stage=parameter_invalid capability=%s", capability.key)
        renewed = {**pending, "expires_at": now + C5_PARAMETER_TTL_MS}
        return C5ControlReply(
            f"请说{capability.label}百分比，范围是"
            f"{capability.minimum_percent}到{capability.maximum_percent}，例如百分之八十。",
            {"c5_parameter_request": renewed, "c5_stage": "awaiting_parameter"},
            [],
        )

    capability = _matched_capability(compact)
    if capability is None:
        return None
    has_control_intent = any(marker in compact for marker in _ON_MARKERS + _OFF_MARKERS + _ADJUST_MARKERS + _AUTO_MARKERS)
    percentage = parse_c5_percentage(
        compact,
        minimum=capability.minimum_percent,
        maximum=capability.maximum_percent,
    )
    if not has_control_intent and percentage is None:
        return None
    block_reason = c5_capability_block_reason(db, site_id, capability)
    if block_reason:
        logger.info("C5 assistant stage=capability_blocked capability=%s", capability.key)
        return C5ControlReply(block_reason, {"c5_stage": "blocked", "c5_capability": capability.key}, [])
    if any(marker in compact for marker in _AUTO_MARKERS):
        return C5ControlReply(
            f"当前未配置补光灯自动控制策略，请直接提供 "
            f"{capability.minimum_percent} 到 {capability.maximum_percent} 的亮度百分比。",
            {"c5_stage": "unsupported_auto_mode", "c5_capability": capability.key},
            [],
        )
    if percentage is not None and capability.accepts_percentage:
        operation = f"把{capability.label}调到 {percentage}%"
        return _confirmation_reply(
            capability,
            _device_action(capability, percentage, operation),
            operation,
        )
    if any(marker in compact for marker in _OFF_MARKERS):
        operation = f"关闭{capability.label}"
        return _confirmation_reply(
            capability,
            _device_action(capability, capability.minimum_percent, operation),
            operation,
        )
    if any(marker in compact for marker in _ON_MARKERS):
        operation = f"打开{capability.label}"
        return _confirmation_reply(
            capability,
            _device_action(capability, capability.maximum_percent, operation),
            operation,
        )
    if capability.accepts_percentage:
        pending_context = _parameter_context(capability, now)
        logger.info("C5 assistant stage=awaiting_parameter capability=%s", capability.key)
        return C5ControlReply(
            f"{capability.label}要调到百分之几？可设置范围是"
            f"{capability.minimum_percent}到{capability.maximum_percent}。",
            {"c5_parameter_request": pending_context, "c5_stage": "awaiting_parameter"},
            [],
        )
    return None
