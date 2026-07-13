import json
import os
import time
import uuid
from typing import Optional, Any
from fastapi import FastAPI, Depends, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
import models
from database import engine, get_db
from ai.deepseek_client import chat
from ai.prompt_builder import build_prompt
from ai.decision_engine import make_decision
from mqtt_broker import start_mqtt_background, publish_command

# 启动时自动检查并在目录下创建数据表
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="SmartAgriBrain-API v1")

# ==========================================
# 知识库预加载逻辑
# ==========================================
KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base", "tomato_rules.json")


def load_knowledge_base():
    if os.path.exists(KNOWLEDGE_PATH):
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    print("⚠️ 知识库文件未找到，请检查路径。")
    return {}


AGRICULTURE_KB = load_knowledge_base()


# ==========================================
# 统一响应包装器 (放宽 data 类型为 Any，解决 List 警告)
# ==========================================
def format_success(data: Any, req_id: Optional[str] = None):
    return {
        "request_id": req_id or str(uuid.uuid4()),
        "data": data
    }


def format_error(code: str, message: str, details: Optional[dict] = None, req_id: Optional[str] = None):
    return {
        "request_id": req_id or str(uuid.uuid4()),
        "error": {
            "code": code,
            "message": message,
            "details": details or {}
        }
    }


# ==========================================
# 数据模型定义
# ==========================================
class CommandRequest(BaseModel):
    source: str
    reason: str
    command: dict
    ttl_seconds: int = 30


class AIAnalysisRequest(BaseModel):
    crop: str = "tomato"
    include_weather: bool = True
    include_history_hours: int = 24


# ==========================================
# 路由接口定义 (100% 对齐 V1 契约，使用 Telemetry 新表)
# ==========================================

@app.on_event("startup")
async def startup_event():
    print("启动智慧农业云端后端服务 (V1标准)...")
    start_mqtt_background()


@app.get("/api/v1/health")
async def health_check():
    """契约 4.3: 健康检查接口"""
    return format_success({"status": "ok", "version": "1.0"})


@app.get("/api/v1/devices/{device_id}/latest")
async def get_latest_data(device_id: str, db: Session = Depends(get_db)):
    """契约 4.3: 获取设备最新遥测数据"""
    record = db.query(models.Telemetry).filter(
        models.Telemetry.device_id == device_id
    ).order_by(models.Telemetry.received_at.desc()).first()

    if not record:
        return format_error("DEVICE_NOT_FOUND", "暂无该设备数据", {"device_id": device_id})

    telemetry_data = {
        "record_id": record.record_id,
        "device_id": record.device_id,
        "sequence": record.sequence,
        "sampled_at": record.sampled_at,
        "received_at": record.received_at,
        "time_quality": "synced",
        "sensors": {
            "temperature_c": record.temperature_c,
            "humidity_pct": record.humidity_pct,
            "pressure_kpa": record.pressure_kpa,
            "gas_resistance_ohm": record.gas_resistance_ohm,
            "illuminance_lux": record.illuminance_lux,
            "co2_ppm": record.co2_ppm,
            "soil_moisture_pct": record.soil_moisture_pct,
            "soil_ec_ms_cm": record.soil_ec_ms_cm
        },
        "quality": record.payload_snapshot.get("quality", {}),
        "actuators": record.payload_snapshot.get("actuators", {}),
        "connectivity": record.payload_snapshot.get("connectivity", {})
    }
    return format_success(telemetry_data)


@app.get("/api/v1/devices/{device_id}/status")
async def get_device_status(device_id: str, db: Session = Depends(get_db)):
    """契约 4.3: 获取设备在线与执行器状态"""
    record = db.query(models.Telemetry).filter(
        models.Telemetry.device_id == device_id
    ).order_by(models.Telemetry.received_at.desc()).first()

    if not record:
        return format_error("DEVICE_NOT_FOUND", "设备离线或无数据", {"device_id": device_id})

    status_data = {
        "device_id": device_id,
        "online": True,
        "last_seen_at": record.received_at,
        "last_telemetry_at": record.sampled_at,
        "connectivity": record.payload_snapshot.get("connectivity", {}),
        "actuators": record.payload_snapshot.get("actuators", {})
    }
    return format_success(status_data)


@app.get("/api/v1/devices/{device_id}/telemetry")
async def get_telemetry_history(
        device_id: str,
        from_time: Optional[int] = Query(None, alias="from"),
        to_time: Optional[int] = Query(None, alias="to"),
        limit: int = Query(100, le=1000),
        db: Session = Depends(get_db)
):
    """契约 4.3: 获取设备历史遥测数据 (供前端渲染图表)"""
    now = int(time.time() * 1000)
    if not to_time:
        to_time = now
    if not from_time:
        from_time = now - 24 * 3600 * 1000

    records = db.query(models.Telemetry).filter(
        models.Telemetry.device_id == device_id,
        models.Telemetry.received_at >= from_time,
        models.Telemetry.received_at <= to_time
    ).order_by(models.Telemetry.received_at.asc()).limit(limit).all()

    data_list = []
    for r in records:
        item = {
            "record_id": r.record_id,
            "device_id": r.device_id,
            "sequence": r.sequence,
            "sampled_at": r.sampled_at,
            "received_at": r.received_at,
            "time_quality": "synced",
            "sensors": {
                "temperature_c": r.temperature_c,
                "humidity_pct": r.humidity_pct,
                "pressure_kpa": r.pressure_kpa,
                "gas_resistance_ohm": r.gas_resistance_ohm,
                "illuminance_lux": r.illuminance_lux,
                "co2_ppm": r.co2_ppm,
                "soil_moisture_pct": r.soil_moisture_pct,
                "soil_ec_ms_cm": r.soil_ec_ms_cm,
            },
            "quality": r.payload_snapshot.get("quality", {}),
            "actuators": r.payload_snapshot.get("actuators", {}),
            "connectivity": r.payload_snapshot.get("connectivity", {})
        }
        data_list.append(item)

    return format_success(data_list)


@app.post("/api/v1/devices/{device_id}/commands", status_code=202)
async def send_command_to_device(device_id: str, req: CommandRequest, db: Session = Depends(get_db)):
    """契约 4.4: 接收前端命令、入库并转交 MQTT 下发"""
    req_id = str(uuid.uuid4())

    cmd_data = publish_command(
        device_id=device_id,
        target=req.command["target"],
        value=req.command["value"],
        source=req.source,
        reason=req.reason
    )

    db_cmd = models.Command(
        command_id=cmd_data["command_id"],
        device_id=device_id,
        state="PUBLISHED",
        source=req.source,
        reason=req.reason,
        operation="set",
        target=req.command["target"],
        value=req.command["value"],
        created_at=cmd_data["issued_at"],
        published_at=int(time.time() * 1000)
    )
    db.add(db_cmd)
    db.commit()

    command_resource = {
        "command_id": db_cmd.command_id,
        "device_id": device_id,
        "state": db_cmd.state,
        "source": req.source,
        "reason": req.reason,
        "command": {"operation": "set", "target": db_cmd.target, "value": db_cmd.value},
        "created_at": db_cmd.created_at,
        "published_at": db_cmd.published_at,
        "completed_at": None,
        "ack": None
    }
    return format_success(command_resource, req_id)


@app.get("/api/v1/devices/{device_id}/commands/{command_id}")
async def get_command_status(device_id: str, command_id: str, db: Session = Depends(get_db)):
    """契约 4.3: 获取单个命令的流转状态与硬件最终 ACK 结果"""
    cmd = db.query(models.Command).filter(
        models.Command.device_id == device_id,
        models.Command.command_id == command_id
    ).first()

    if not cmd:
        return format_error("DEVICE_NOT_FOUND", "未找到该指令记录", {"command_id": command_id})

    ack = db.query(models.CommandAck).filter(models.CommandAck.command_id == command_id).first()
    ack_data = None
    if ack:
        ack_data = {
            "acknowledged_at": ack.acknowledged_at,
            "state": ack.state,
            "actual_value": ack.actual_value,
            "error": {"code": ack.error_code} if ack.error_code else None
        }

    res = {
        "command_id": cmd.command_id,
        "device_id": cmd.device_id,
        "state": cmd.state,
        "source": cmd.source,
        "reason": cmd.reason,
        "command": {
            "operation": cmd.operation,
            "target": cmd.target,
            "value": cmd.value
        },
        "created_at": cmd.created_at,
        "published_at": cmd.published_at,
        "completed_at": cmd.completed_at,
        "ack": ack_data
    }
    return format_success(res)


@app.post("/api/v1/vision/disease")
async def detect_disease(file: UploadFile = File(...)):
    """契约 4.6: 视觉病害识别"""
    await file.read()
    req_id = str(uuid.uuid4())

    mock_result = {
        "detection_id": str(uuid.uuid4()),
        "photo_id": "mock_photo_001",
        "diagnosis": "downy_mildew",
        "disease_name_zh": "霜霉病",
        "confidence": 0.87,
        "affected_area_ratio": 0.15,
        "detections": [
            {"label": "downy_mildew", "confidence": 0.87, "bbox": {"x": 120, "y": 45, "width": 90, "height": 115}}
        ],
        "summary": "发现霜霉病迹象",
        "suggestions": ["加强通风降湿"],
        "processed_at": int(time.time() * 1000)
    }
    return format_success(mock_result, req_id)


@app.post("/api/v1/devices/{device_id}/analyses")
async def analyze_ai(device_id: str, req: AIAnalysisRequest, db: Session = Depends(get_db)):
    """契约 4.6: AI 综合分析"""
    record = db.query(models.Telemetry).filter(
        models.Telemetry.device_id == device_id
    ).order_by(models.Telemetry.received_at.desc()).first()

    if not record:
        return format_error("DEVICE_NOT_FOUND", "暂无设备数据无法分析", {"device_id": device_id})

    sensor_data = {
        "temperature": record.temperature_c,
        "humidity": record.humidity_pct,
        "pressure": record.pressure_kpa,
        "gas_resistance": record.gas_resistance_ohm
    }

    prompt = build_prompt(sensor_data, AGRICULTURE_KB)
    raw_result = chat(prompt)
    decision = make_decision(raw_result, sensor_data)

    analysis_result = {
        "analysis_id": str(uuid.uuid4()),
        "device_id": device_id,
        "crop": req.crop,
        "risk_level": "low",
        "risk_score": 18,
        "risk_status": "环境稳定",
        "summary": decision.get("summary", "当前环境稳定。"),
        "suggestions": decision.get("suggestions", []),
        "proposed_commands": [],
        "created_at": int(time.time() * 1000)
    }
    return format_success(analysis_result)