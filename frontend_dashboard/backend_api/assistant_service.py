from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

from deepseek_service import call_deepseek_chat, deepseek_api_key, strip_code_fence
from schemas import (
    AssistantAction,
    AssistantChatMessage,
    AssistantChatRequest,
    AssistantChatResponse,
    KnowledgeReference,
)


ALLOWED_VIEWS = {"overview", "realtime", "history", "disease", "ai", "control", "knowledge", "alarms"}
ALLOWED_PANELS = {"assistant", "smart_control", "knowledge", "disease_upload"}
ALLOWED_DEVICE_COMMANDS = {
    "fan_on",
    "fan_off",
    "pump_on",
    "pump_off",
    "light_on",
    "light_off",
    "curtain_open",
    "curtain_close",
    "alarm_on",
    "alarm_off",
}
ALLOWED_SMART_OPS = {"enable", "disable", "all_auto", "open_panel", "set_manual", "update_manual", "restore_auto"}
ALLOWED_SMART_KEYS = {"water", "light", "heat", "cool", "vent", "co2"}
ALLOWED_KB_OPS = {"create", "update", "delete", "select"}


def now_ms() -> int:
    return int(time.time() * 1000)


def safe_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def clamp_percent(value: Any) -> int:
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, number))


def compact_context(value: Any, limit: int = 3600) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def action_risk(action_type: str, payload: Dict[str, Any]) -> str:
    if action_type == "device_command":
        return "high"
    if action_type == "smart_control":
        return "high" if payload.get("operation") == "disable" else "medium"
    if action_type in {"knowledge_base", "knowledge_item"} and payload.get("operation") == "delete":
        return "high"
    if action_type in {"knowledge_base", "knowledge_item"}:
        return "medium"
    return "normal"


def default_title(action_type: str) -> str:
    titles = {
        "navigate_view": "切换页面",
        "open_panel": "打开面板",
        "device_command": "设备控制",
        "smart_control": "调整智能托管",
        "knowledge_base": "操作知识库",
        "knowledge_item": "操作知识条目",
        "run_knowledge_analysis": "生成知识库分析",
        "refresh_data": "刷新数据",
    }
    return titles.get(action_type, "建议操作")


def sanitize_device_action(raw_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    command = safe_text(raw_payload.get("command"))
    if command not in ALLOWED_DEVICE_COMMANDS:
        return None
    raw_value = raw_payload.get("value")
    if raw_value is None:
        raw_value = 0 if command.endswith("_off") or command == "curtain_close" else 1
    value = 1 if safe_int(raw_value, 1) > 0 else 0
    return {
        "command": command,
        "value": value,
        "reason": safe_text(raw_payload.get("reason"), "AI助手建议执行设备控制")[:160],
    }


def sanitize_smart_control_action(raw_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    operation = safe_text(raw_payload.get("operation"))
    if operation not in ALLOWED_SMART_OPS:
        return None
    payload: Dict[str, Any] = {"operation": operation}
    key = safe_text(raw_payload.get("key"))
    if operation in {"set_manual", "update_manual", "restore_auto"}:
        if key not in ALLOWED_SMART_KEYS:
            return None
        payload["key"] = key
    if operation == "update_manual":
        payload["value"] = clamp_percent(raw_payload.get("value"))
    return payload


def sanitize_knowledge_payload(raw_payload: Dict[str, Any], item: bool) -> Optional[Dict[str, Any]]:
    operation = safe_text(raw_payload.get("operation"))
    if operation not in ALLOWED_KB_OPS:
        return None
    payload: Dict[str, Any] = {"operation": operation}

    kb_id = safe_int(raw_payload.get("kbId") or raw_payload.get("kb_id"))
    if operation in {"update", "delete", "select"} and kb_id <= 0:
        return None
    if kb_id > 0:
        payload["kbId"] = kb_id

    if item:
        item_id = safe_int(raw_payload.get("itemId") or raw_payload.get("item_id"))
        if operation in {"update", "delete", "select"} and item_id <= 0:
            return None
        if item_id > 0:
            payload["itemId"] = item_id
        title = safe_text(raw_payload.get("title"))
        content = safe_text(raw_payload.get("content"))
        if operation in {"create", "update"} and (not title or not content):
            return None
        if title:
            payload["title"] = title[:120]
        if content:
            payload["content"] = content[:1200]
    else:
        name = safe_text(raw_payload.get("name"))
        description = safe_text(raw_payload.get("description"))
        if operation in {"create", "update"} and not name:
            return None
        if name:
            payload["name"] = name[:80]
        if description:
            payload["description"] = description[:400]

    return payload


def sanitize_action(raw: Any, index: int) -> Optional[AssistantAction]:
    if not isinstance(raw, dict):
        return None
    action_type = safe_text(raw.get("type") or raw.get("actionType") or raw.get("action"))
    raw_payload = raw.get("payload")
    if not isinstance(raw_payload, dict):
        raw_payload = {}

    payload: Optional[Dict[str, Any]]
    if action_type == "navigate_view":
        view = safe_text(raw_payload.get("view"))
        payload = {"view": view} if view in ALLOWED_VIEWS else None
    elif action_type == "open_panel":
        panel = safe_text(raw_payload.get("panel"))
        payload = {"panel": panel} if panel in ALLOWED_PANELS else None
    elif action_type == "device_command":
        payload = sanitize_device_action(raw_payload)
    elif action_type == "smart_control":
        payload = sanitize_smart_control_action(raw_payload)
    elif action_type == "knowledge_base":
        payload = sanitize_knowledge_payload(raw_payload, item=False)
    elif action_type == "knowledge_item":
        payload = sanitize_knowledge_payload(raw_payload, item=True)
    elif action_type == "run_knowledge_analysis":
        question = safe_text(raw_payload.get("question"))
        kb_id = safe_int(raw_payload.get("kbId") or raw_payload.get("kb_id"))
        payload = {}
        if question:
            payload["question"] = question[:300]
        if kb_id > 0:
            payload["kbId"] = kb_id
    elif action_type == "refresh_data":
        payload = {}
    else:
        payload = None

    if payload is None:
        return None

    return AssistantAction(
        id=f"assistant-action-{now_ms()}-{index}",
        type=action_type,  # type: ignore[arg-type]
        title=safe_text(raw.get("title") or raw.get("label"), default_title(action_type))[:80],
        description=safe_text(raw.get("description"), "")[:240],
        risk=action_risk(action_type, payload),  # type: ignore[arg-type]
        payload=payload,
    )


def sanitize_actions(raw_actions: Any) -> List[AssistantAction]:
    if not isinstance(raw_actions, list):
        return []

    actions: List[AssistantAction] = []
    for index, raw in enumerate(raw_actions):
        action = sanitize_action(raw, index)
        if action is not None:
            actions.append(action)
        if len(actions) >= 3:
            break
    return actions


def references_from_payload(payload: AssistantChatRequest) -> List[KnowledgeReference]:
    references: List[KnowledgeReference] = []
    kb_id = payload.knowledge_base_id
    for index, item in enumerate(payload.knowledge_items[:5], start=1):
        if kb_id and item.get("kbId") != kb_id:
            continue
        title = safe_text(item.get("title"), "知识条目")
        content = safe_text(item.get("content"))
        if not content:
            continue
        references.append(
            KnowledgeReference(
                itemId=safe_int(item.get("itemId"), index),
                chunkId=index,
                title=title[:120],
                content=content[:360],
                score=max(0.5, 0.95 - index * 0.08),
            )
        )
    return references


def build_assistant_prompt(payload: AssistantChatRequest, references: List[KnowledgeReference]) -> str:
    context = {
        "question": payload.question,
        "currentView": payload.current_view,
        "imageUrl": payload.image_url,
        "latest": payload.latest,
        "disease": payload.disease,
        "knowledgeBaseId": payload.knowledge_base_id,
        "knowledgeReferences": [reference.model_dump(mode="json") for reference in references],
        "knowledgeBases": payload.knowledge_bases[:8],
        "commandResults": payload.command_results[:5],
    }
    return (
        "你是 SmartAgriBrain 智慧农业 Web 平台的 AI 助手。"
        "你可以回答农事问题，也可以提出界面操作或设备控制建议，但永远不能声称已经执行。"
        "所有操作都必须作为 actions 返回，等待用户在前端确认。只输出合法 JSON，不要 Markdown。"
        "\n输出格式：{\"answer\":\"给用户看的中文回答\",\"actions\":[...]}"
        "\n每个 action 格式：{\"type\":\"...\",\"title\":\"...\",\"description\":\"...\",\"payload\":{...}}"
        "\n允许的 action："
        "\n1 navigate_view: {\"view\":\"overview|realtime|history|disease|ai|control|knowledge|alarms\"}"
        "\n2 open_panel: {\"panel\":\"assistant|smart_control|knowledge|disease_upload\"}"
        "\n3 device_command: {\"command\":\"fan_on|fan_off|pump_on|pump_off|light_on|light_off|curtain_open|curtain_close|alarm_on|alarm_off\",\"value\":0或1,\"reason\":\"原因\"}"
        "\n4 smart_control: {\"operation\":\"enable|disable|all_auto|open_panel|set_manual|update_manual|restore_auto\",\"key\":\"water|light|heat|cool|vent|co2\",\"value\":0到100}"
        "\n5 knowledge_base: {\"operation\":\"create|update|delete|select\",\"kbId\":数字,\"name\":\"名称\",\"description\":\"描述\"}"
        "\n6 knowledge_item: {\"operation\":\"create|update|delete|select\",\"kbId\":数字,\"itemId\":数字,\"title\":\"标题\",\"content\":\"正文\"}"
        "\n7 run_knowledge_analysis: {\"kbId\":数字,\"question\":\"分析问题\"}"
        "\n8 refresh_data: {}"
        "\n最多返回 3 个 actions。涉及设备开关、报警器、删除或关闭托管时，回答里必须提醒用户确认风险。"
        f"\n当前上下文：{compact_context(context)}"
    )


def parse_model_content(content: str) -> Tuple[str, List[AssistantAction]]:
    parsed = json.loads(strip_code_fence(content))
    if not isinstance(parsed, dict):
        raise ValueError("assistant response must be a JSON object")
    answer = safe_text(parsed.get("answer"), "我已收到问题，但暂时没有生成可靠回答。")
    return answer[:1600], sanitize_actions(parsed.get("actions"))


def local_reply(payload: AssistantChatRequest, message: str, references: Optional[List[KnowledgeReference]] = None) -> AssistantChatResponse:
    now = now_ms()
    chat_message = AssistantChatMessage(
        id=f"assistant-{now}",
        content=message,
        created_at=now,
        references=references or [],
        suggested_actions=[],
    )
    return AssistantChatResponse(message=chat_message, references=references or [], actions=[])


def not_configured_reply(payload: AssistantChatRequest) -> AssistantChatResponse:
    latest = payload.latest if isinstance(payload.latest, dict) else {}
    sensors = latest.get("sensors") if isinstance(latest, dict) else {}
    sensor_text = ""
    if isinstance(sensors, dict) and sensors:
        sensor_text = (
            f"\n\n当前环境参考：温度 {sensors.get('temperature', '--')}℃，"
            f"湿度 {sensors.get('humidity', '--')}%RH，"
            f"光照 {sensors.get('light', '--')}lux，"
            f"CO2 {sensors.get('co2', '--')}ppm。"
        )
    return local_reply(
        payload,
        "AI助手后端还没有配置 DeepSeek API Key。配置后，我会基于实时环境、病害结果和知识库内容生成真实问答与待确认操作建议。"
        f"{sensor_text}\n\n你的问题：{payload.question}",
        references_from_payload(payload),
    )


def assistant_chat(payload: AssistantChatRequest) -> AssistantChatResponse:
    references = references_from_payload(payload)
    if not deepseek_api_key():
        return not_configured_reply(payload)

    try:
        content = call_deepseek_chat(
            [
                {
                    "role": "system",
                    "content": "你是智慧农业 Web 助手，只输出合法 JSON；所有动作只作为待确认建议返回。",
                },
                {
                    "role": "user",
                    "content": build_assistant_prompt(payload, references),
                },
            ],
            max_tokens=1000,
            timeout_seconds=90,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        answer, actions = parse_model_content(content)
    except Exception as error:
        print(f"assistant chat fallback: {error}")
        return local_reply(payload, "AI助手暂时没有拿到可靠回复。请稍后重试，或先使用当前页面的手动控制与知识库分析功能。", references)

    now = now_ms()
    chat_message = AssistantChatMessage(
        id=f"assistant-{now}",
        content=answer,
        created_at=now,
        references=references,
        suggested_actions=actions,
    )
    return AssistantChatResponse(message=chat_message, references=references, actions=actions)
