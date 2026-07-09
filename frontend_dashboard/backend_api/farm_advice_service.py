from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Literal, Optional, Tuple

from deepseek_service import call_deepseek_chat, deepseek_api_key, strip_code_fence
from schemas import AiCommand, AiRiskFactor, FarmAdviceRequest, FarmAdviceResponse


RiskLevel = Literal["low", "medium", "high"]

ALLOWED_COMMANDS = {
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


def now_ms() -> int:
    return int(time.time() * 1000)


def safe_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_number(value: float) -> str:
    return f"{value:g}"


def clamp_list(value: Any, limit: int, item_limit: int = 120) -> List[str]:
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
        items.append(text[:item_limit])
        if len(items) >= limit:
            break
    return items


def sanitize_risk(value: Any, fallback: RiskLevel) -> RiskLevel:
    text = safe_text(value).lower()
    if text in {"low", "medium", "high"}:
        return text  # type: ignore[return-value]
    if text in {"正常", "低", "良好"}:
        return "low"
    if text in {"中", "注意", "预警"}:
        return "medium"
    if text in {"高", "危险", "严重"}:
        return "high"
    return fallback


def risk_status_from_score(score: int) -> str:
    if score >= 70:
        return "高风险"
    if score >= 35:
        return "需关注"
    return "较稳定"


def risk_level_from_score(score: int) -> RiskLevel:
    if score >= 70:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def risk_score_from_level(level: RiskLevel) -> int:
    if level == "high":
        return 82
    if level == "medium":
        return 54
    return 18


def sanitize_risk_score(value: Any, fallback: int) -> int:
    try:
        score = round(float(value))
    except (TypeError, ValueError):
        score = fallback
    return max(0, min(100, score))


def sanitize_factor_state(value: Any) -> str:
    text = safe_text(value).lower()
    if text in {"good", "watch", "danger", "neutral"}:
        return text
    if text in {"正常", "稳定", "良好", "低"}:
        return "good"
    if text in {"高", "危险", "严重"}:
        return "danger"
    return "watch"


def sanitize_risk_factors(value: Any, fallback: List[AiRiskFactor]) -> List[AiRiskFactor]:
    if not isinstance(value, list):
        return fallback

    factors: List[AiRiskFactor] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            label = item[:40]
            detail = item[:120]
            state = "watch"
            key = f"factor_{index + 1}"
        elif isinstance(item, dict):
            label = safe_text(item.get("label") or item.get("name") or item.get("title"), "风险项")[:40]
            detail = safe_text(item.get("detail") or item.get("reason") or item.get("description"), label)[:140]
            state = sanitize_factor_state(item.get("state") or item.get("level"))
            key = safe_text(item.get("key"), f"factor_{index + 1}")[:40]
        else:
            continue
        factors.append(AiRiskFactor(key=key, label=label, detail=detail, state=state))  # type: ignore[arg-type]
        if len(factors) >= 3:
            break
    return factors or fallback


def sanitize_commands(value: Any) -> List[AiCommand]:
    if not isinstance(value, list):
        return []

    commands: List[AiCommand] = []
    for item in value:
        if isinstance(item, str):
            command = item.strip()
            raw_value = None
        elif isinstance(item, dict):
            command = safe_text(item.get("command") or item.get("action"))
            raw_value = item.get("value")
        else:
            continue

        if command not in ALLOWED_COMMANDS:
            continue
        if raw_value is None:
            raw_value = 0 if command.endswith("_off") or command == "curtain_close" else 1
        try:
            command_value = 1 if int(float(raw_value)) > 0 else 0
        except (TypeError, ValueError):
            command_value = 1
        commands.append(AiCommand(command=command, value=command_value))
        if len(commands) >= 3:
            break
    return commands


def metric_line(label: str, value: Optional[float], unit: str, target: str) -> str:
    if value is None:
        return f"{label}暂无有效读数"
    return f"{label}{format_number(value)}{unit}，建议区间{target}"


def add_factor(factors: List[AiRiskFactor], key: str, label: str, detail: str, state: str) -> None:
    factors.append(AiRiskFactor(key=key, label=label, detail=detail, state=state))  # type: ignore[arg-type]


def evaluate_sensors(sensors: Dict[str, Any]) -> Tuple[RiskLevel, int, List[AiRiskFactor], List[str], List[str], List[AiCommand]]:
    temperature = safe_float(sensors.get("temperature"))
    humidity = safe_float(sensors.get("humidity"))
    light = safe_float(sensors.get("light"))
    co2 = safe_float(sensors.get("co2"))
    soil_moisture = safe_float(sensors.get("soil_moisture"))
    soil_ec = safe_float(sensors.get("soil_ec"))

    risk_score = 0
    risk_points = 0
    factors: List[AiRiskFactor] = []
    suggestions: List[str] = []
    basis: List[str] = []
    commands: List[AiCommand] = []

    basis.extend(
        [
            metric_line("温度", temperature, "℃", "24-30℃"),
            metric_line("空气湿度", humidity, "%RH", "55-70%RH"),
            metric_line("光照", light, "lux", "14000-24000lux"),
            metric_line("CO2", co2, "ppm", "520-900ppm"),
            metric_line("土壤湿度", soil_moisture, "%", "45-65%"),
        ]
    )
    if soil_ec is not None:
        basis.append(metric_line("土壤EC", soil_ec, "mS/cm", "1.2-2.4mS/cm"))

    if temperature is not None:
        if temperature >= 34:
            risk_score += 3
            risk_points += 34
            add_factor(factors, "temperature", "温度过高", "温度明显高于目标，优先通风降温。", "danger")
            suggestions.append("温度明显偏高，先通风降温 5-10 分钟，复查温度回落趋势。")
            commands.append(AiCommand(command="fan_on", value=1))
        elif temperature > 30:
            risk_score += 2
            risk_points += 24
            add_factor(factors, "temperature", "温度偏高", "温度高于目标上限，建议短时通风或遮光。", "watch")
            suggestions.append("温度高于目标上限，优先短时通风或适度遮光，避免继续升温。")
            commands.append(AiCommand(command="fan_on", value=1))
        elif temperature < 20:
            risk_score += 2
            risk_points += 24
            add_factor(factors, "temperature", "温度偏低", "温度低于适宜范围，注意保温。", "watch")
            suggestions.append("温度偏低，减少通风并保持保温，20 分钟后复查。")
            commands.append(AiCommand(command="fan_off", value=0))
        elif temperature < 24:
            risk_score += 1
            risk_points += 12
            add_factor(factors, "temperature", "温度略低", "温度略低于目标，暂不建议大幅通风。", "watch")
            suggestions.append("温度略低，保持保温策略，暂不做大幅通风。")

    if humidity is not None:
        if humidity >= 85:
            risk_score += 3
            risk_points += 34
            add_factor(factors, "humidity", "湿度过高", "高湿会增加叶面结露和病害风险。", "danger")
            suggestions.append("空气湿度过高，立即短时通风降湿，减少叶面结露和霜霉风险。")
            commands.append(AiCommand(command="fan_on", value=1))
        elif humidity > 72:
            risk_score += 2
            risk_points += 24
            add_factor(factors, "humidity", "湿度偏高", "湿度高于目标，建议先通风降湿。", "watch")
            suggestions.append("空气湿度偏高，建议通风 5 分钟并减少喷淋。")
            commands.append(AiCommand(command="fan_on", value=1))
        elif humidity < 40:
            risk_score += 1
            risk_points += 12
            add_factor(factors, "humidity", "湿度偏低", "空气偏干，注意补水后的蒸腾变化。", "watch")
            suggestions.append("空气湿度偏低，注意补水后观察蒸腾变化。")

    if soil_moisture is not None:
        if soil_moisture < 35:
            risk_score += 3
            risk_points += 34
            add_factor(factors, "soil_moisture", "土壤缺水", "土壤湿度明显不足，需少量补水并复查。", "danger")
            suggestions.append("土壤湿度明显不足，建议补水 3-5 分钟，10 分钟后复查。")
            commands.append(AiCommand(command="pump_on", value=1))
        elif soil_moisture < 45:
            risk_score += 2
            risk_points += 24
            add_factor(factors, "soil_moisture", "土壤偏干", "土壤湿度低于目标，建议小水量补充。", "watch")
            suggestions.append("土壤湿度低于目标，少量补水并避免一次灌溉过量。")
            commands.append(AiCommand(command="pump_on", value=1))
        elif soil_moisture > 75:
            risk_score += 2
            risk_points += 24
            add_factor(factors, "soil_moisture", "土壤偏湿", "土壤湿度偏高，暂停补水并检查排水。", "watch")
            suggestions.append("土壤湿度偏高，暂停补水并检查排水。")
            commands.append(AiCommand(command="pump_off", value=0))

    if light is not None:
        if light < 10000:
            risk_score += 2
            risk_points += 22
            add_factor(factors, "light", "光照不足", "光照明显低于目标，影响光合作用。", "watch")
            suggestions.append("光照不足，优先打开卷帘获取自然光，必要时补光 15-30 分钟。")
            commands.append(AiCommand(command="curtain_open", value=1))
        elif light < 14000:
            risk_score += 1
            risk_points += 12
            add_factor(factors, "light", "光照略低", "光照略低，可短时补光观察。", "watch")
            suggestions.append("光照略低，可短时补光并观察叶片状态。")
            commands.append(AiCommand(command="light_on", value=1))
        elif light > 32000:
            risk_score += 2
            risk_points += 22
            add_factor(factors, "light", "光照过强", "强光可能造成叶片灼伤，建议适度遮光。", "watch")
            suggestions.append("光照过强，建议适度遮光，避免叶片灼伤。")
            commands.append(AiCommand(command="light_off", value=0))

    if co2 is not None:
        if co2 < 420:
            risk_score += 1
            risk_points += 10
            add_factor(factors, "co2", "CO2偏低", "CO2 低于适宜范围，结合通风状态处理。", "watch")
            suggestions.append("CO2 偏低，减少无效长时间通风，结合光照补充气肥。")
        elif co2 > 1200:
            risk_score += 2
            risk_points += 22
            add_factor(factors, "co2", "CO2偏高", "CO2 浓度偏高，需短时通风稀释。", "watch")
            suggestions.append("CO2 偏高，短时通风稀释并观察浓度变化。")
            commands.append(AiCommand(command="fan_on", value=1))

    if soil_ec is not None:
        if soil_ec > 2.8:
            risk_score += 3
            risk_points += 32
            add_factor(factors, "soil_ec", "EC过高", "土壤 EC 明显偏高，有盐害风险。", "danger")
            suggestions.append("土壤 EC 明显偏高，暂停追肥并用清水小量淋洗，复查盐分。")
        elif soil_ec > 2.4:
            risk_score += 2
            risk_points += 22
            add_factor(factors, "soil_ec", "EC偏高", "土壤 EC 偏高，降低施肥浓度。", "watch")
            suggestions.append("土壤 EC 偏高，降低施肥浓度并观察植株边缘灼伤。")
        elif soil_ec < 1.0:
            risk_score += 1
            risk_points += 10
            add_factor(factors, "soil_ec", "EC偏低", "土壤 EC 偏低，可小幅补充营养液。", "watch")
            suggestions.append("土壤 EC 偏低，后续可小幅补充营养液。")

    if risk_score >= 5:
        risk: RiskLevel = "high"
    elif risk_score >= 2:
        risk = "medium"
    else:
        risk = "low"

    if not suggestions:
        suggestions.append("当前主要指标接近目标区间，保持现有策略并每 30 分钟复查一次。")
    if not factors:
        add_factor(factors, "stable", "环境稳定", "关键指标处于目标范围内，保持当前策略。", "good")

    deduped_commands: List[AiCommand] = []
    seen_commands = set()
    for command in commands:
        key = (command.command, command.value)
        if key in seen_commands:
            continue
        seen_commands.add(key)
        deduped_commands.append(command)
        if len(deduped_commands) >= 3:
            break

    score = max(risk_score_from_level(risk), min(100, risk_points)) if risk != "low" else min(34, max(12, risk_points))
    return risk, score, factors[:3], suggestions[:4], basis[:8], deduped_commands


def fallback_advice(payload: FarmAdviceRequest) -> FarmAdviceResponse:
    sensors = payload.sensors if isinstance(payload.sensors, dict) else {}
    risk, score, factors, suggestions, basis, commands = evaluate_sensors(sensors)
    summary_prefix = {
        "low": "当前农情整体稳定",
        "medium": "当前农情存在轻中度偏离",
        "high": "当前农情存在较高风险",
    }[risk]
    return FarmAdviceResponse(
        device_id=payload.device_id,
        crop=payload.crop,
        ai_connected=True,
        risk_level=risk,
        risk_score=score,
        risk_status=risk_status_from_score(score),
        risk_factors=factors,
        summary=f"{summary_prefix}，建议按传感器偏离项做小幅调控并复查。",
        suggestions=suggestions,
        commands=commands,
        basis=basis,
        updated_at=now_ms(),
    )


def disconnected_advice(payload: FarmAdviceRequest, detail: str) -> FarmAdviceResponse:
    return FarmAdviceResponse(
        device_id=payload.device_id,
        crop=payload.crop,
        ai_connected=False,
        risk_level="low",
        risk_score=0,
        risk_status="AI 未连接",
        risk_factors=[
            AiRiskFactor(
                key="ai_disconnected",
                label="AI 未连接",
                detail=detail,
                state="neutral",
            )
        ],
        summary="AI 未连接，暂时无法生成风险指数和农事建议。",
        suggestions=["请配置 DeepSeek API Key 并重启后端服务后再生成 AI 分析。"],
        commands=[],
        basis=["未连接 DeepSeek API，本次未生成 AI 分析结果。"],
        updated_at=now_ms(),
    )


def build_farm_advice_prompt(payload: FarmAdviceRequest, fallback: FarmAdviceResponse) -> str:
    context = {
        "device_id": payload.device_id,
        "crop": payload.crop,
        "sensors": payload.sensors,
        "status": payload.status,
        "local_rule_baseline": fallback.model_dump(mode="json"),
    }
    return (
        "你是温室智慧农业农事顾问。请根据传感器数据生成面向种植者的农事建议。"
        "只输出合法 JSON，不要 Markdown，不要声称已经执行任何设备动作。"
        "\n输出格式固定为："
        "{\"risk_level\":\"low|medium|high\",\"risk_score\":0到100的整数,\"risk_status\":\"较稳定|需关注|高风险\","
        "\"risk_factors\":[{\"key\":\"humidity\",\"label\":\"湿度偏高\",\"detail\":\"为什么需要关注\",\"state\":\"good|watch|danger|neutral\"}],"
        "\"summary\":\"一句话判断\",\"suggestions\":[\"建议1\"],\"commands\":[{\"command\":\"fan_on\",\"value\":1}],\"basis\":[\"依据1\"]}"
        "\n要求："
        "\n1. risk_score 必须让普通用户容易理解：0-34 较稳定，35-69 需关注，70-100 高风险。"
        "\n2. risk_factors 返回 1-3 条，只写最重要原因；如果环境稳定，返回一条 state=good 的稳定原因。"
        "\n3. suggestions 返回 2-4 条，每条必须具体、可执行，包含幅度或复查时间。"
        "\n4. commands 最多 3 条，只能使用 fan_on、fan_off、pump_on、pump_off、light_on、light_off、curtain_open、curtain_close、alarm_on、alarm_off，value 只能是 0 或 1。"
        "\n5. 如果不需要立刻控制设备，commands 返回空数组。"
        "\n6. basis 返回 3-6 条，必须引用输入里的真实传感器数值或设备状态。"
        "\n7. 涉及高温、高湿、低土壤湿度、强光或病害诱因时，风险等级和 risk_score 要相应提高。"
        f"\n当前输入：{json.dumps(context, ensure_ascii=False)}"
    )


def parse_deepseek_advice(content: str, payload: FarmAdviceRequest, fallback: FarmAdviceResponse) -> FarmAdviceResponse:
    parsed = json.loads(strip_code_fence(content))
    if not isinstance(parsed, dict):
        raise ValueError("DeepSeek advice response must be a JSON object")

    summary = safe_text(parsed.get("summary"), fallback.summary)[:180]
    suggestions = clamp_list(parsed.get("suggestions"), 4)
    basis = clamp_list(parsed.get("basis"), 6)
    commands = sanitize_commands(parsed.get("commands"))
    fallback_score = risk_score_from_level(fallback.risk_level)
    score = sanitize_risk_score(parsed.get("risk_score"), fallback.risk_score or fallback_score)
    risk_level = risk_level_from_score(score)
    risk_factors = sanitize_risk_factors(parsed.get("risk_factors"), fallback.risk_factors)
    risk_status = risk_status_from_score(score)

    if not suggestions:
        suggestions = fallback.suggestions
    if not basis:
        basis = fallback.basis

    return FarmAdviceResponse(
        device_id=payload.device_id,
        crop=payload.crop,
        ai_connected=True,
        risk_level=risk_level,
        risk_score=score,
        risk_status=risk_status,
        risk_factors=risk_factors,
        summary=summary,
        suggestions=suggestions,
        commands=commands,
        basis=basis,
        updated_at=now_ms(),
    )


def analyze_farm_advice(payload: FarmAdviceRequest) -> FarmAdviceResponse:
    fallback = fallback_advice(payload)
    if not deepseek_api_key():
        return disconnected_advice(payload, "后端未配置 DeepSeek API Key。")

    try:
        content = call_deepseek_chat(
            [
                {
                    "role": "system",
                    "content": "你是专业农业分析师，只输出合法 JSON，设备动作只能作为待确认建议。",
                },
                {
                    "role": "user",
                    "content": build_farm_advice_prompt(payload, fallback),
                },
            ],
            max_tokens=900,
            timeout_seconds=90,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return parse_deepseek_advice(content, payload, fallback)
    except Exception as error:
        print(f"DeepSeek farm advice unavailable: {error}")
        return disconnected_advice(payload, "DeepSeek API 调用失败，请检查 Key、网络或模型配置。")
