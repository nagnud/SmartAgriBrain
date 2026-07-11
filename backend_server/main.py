import json
import os
from fastapi import FastAPI, Depends, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
import models
from database import engine, get_db
from ai.deepseek_client import chat
from ai.prompt_builder import build_prompt
from ai.decision_engine import make_decision

# 启动时自动检查并在目录下创建 agri_brain.db 及数据表
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="SmartAgriBrain Cloud API")

# ==========================================
# 知识库预加载逻辑 (新增部分)
# ==========================================
KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base", "tomato_rules.json")


def load_knowledge_base():
    """启动时将本地 JSON 知识库加载到内存"""
    if os.path.exists(KNOWLEDGE_PATH):
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    print("⚠️ 知识库文件未找到，请检查路径。")
    return {}


AGRICULTURE_KB = load_knowledge_base()


# ==========================================
# 1. 数据模型定义 (入参约束)
# ==========================================
class SensorData(BaseModel):
    temperature: float
    humidity: float
    pressure: float
    gas_resistance: float
    acc_x: float
    acc_y: float
    acc_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    mag_x: float
    mag_y: float
    mag_z: float


class StatusData(BaseModel):
    wifi: str
    mqtt: str
    fan: int
    pump: int
    light: int


class TelemetryPayload(BaseModel):
    device_id: str
    timestamp: int
    sensors: SensorData
    status: StatusData


class CommandPayload(BaseModel):
    device_id: str
    command: str
    value: int
    reason: Optional[str] = None


# ==========================================
# 2. 核心路由/接口定义
# ==========================================
@app.post("/api/device/telemetry")
async def receive_telemetry(data: TelemetryPayload, db: Session = Depends(get_db)):
    """接收端侧数据并持久化到 SQLite"""
    db_record = models.TelemetryRecord(
        device_id=data.device_id,
        timestamp=data.timestamp,
        temperature=data.sensors.temperature,
        humidity=data.sensors.humidity,
        pressure=data.sensors.pressure,
        gas_resistance=data.sensors.gas_resistance,
        wifi_status=data.status.wifi,
        mqtt_status=data.status.mqtt,
        fan_status=data.status.fan
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    print(f"[数据入库成功] 记录ID: {db_record.id} | 设备: {data.device_id} | 温度: {data.sensors.temperature}°C")
    return {"status": "success", "record_id": db_record.id}


@app.get("/api/device/history")
async def get_history_data(device_id: str = "sensairshuttle_001", limit: int = 10, db: Session = Depends(get_db)):
    """查询设备历史数据（倒序返回最新 N 条）"""
    records = db.query(models.TelemetryRecord).filter(
        models.TelemetryRecord.device_id == device_id
    ).order_by(models.TelemetryRecord.timestamp.desc()).limit(limit).all()

    return {"status": "success", "data": records}


@app.post("/api/device/command")
async def send_command(data: CommandPayload):
    """向端侧下发控制命令"""
    print(f"[指令下发] 目标设备: {data.device_id} | 动作: {data.command}={data.value}")
    return {"status": "success", "command_dispatched": data.model_dump()}


# ==========================================
# 3. 知识库与智能分析路由 (新增部分)
# ==========================================
@app.get("/api/knowledge/match")
async def match_knowledge(current_temp: float, current_hum: float, crop: str = "tomato"):
    """基于当前传感器数据，从知识库中粗筛风险规则"""
    kb = AGRICULTURE_KB
    if not kb or kb.get("crop") != crop:
        return {"status": "error", "message": "无匹配作物的知识库"}

    warnings = []
    matched_rules = []

    # 1. 阈值判定
    thresholds = kb.get("environmental_thresholds", {})
    if current_hum > thresholds.get("humidity", {}).get("warning", 85.0):
        warnings.append("湿度过高，进入高危区间")
        # 2. 匹配对应病害经验
        for disease in kb.get("diseases", []):
            if "湿度高于85%" in disease.get("risk_condition", ""):
                matched_rules.append(disease)

    return {
        "status": "success",
        "warnings": warnings,
        "matched_rules": matched_rules
    }


# ==========================================
# 4. 视觉与图像识别路由 (新增部分)
# ==========================================
@app.post("/api/vision/detect")
async def detect_disease(file: UploadFile = File(...)):
    """
    接收摄像头或前端上传的作物叶片图片，返回 YOLO 结构化识别结果。
    [当前处于 Mock 阶段，供前端联调使用]
    """
    # 1. 读取并验证文件
    file_bytes = await file.read()
    file_size_kb = len(file_bytes) / 1024
    print(f"[图像接收成功] 文件名: {file.filename} | 大小: {file_size_kb:.2f} KB")

    # 2. 按照《项目介绍》约定的结构，返回模拟的 YOLO 识别结果
    mock_yolo_result = {
        "status": "success",
        "file_name": file.filename,
        "diagnosis": "downy_mildew",  # 类别标识
        "disease_name_zh": "霜霉病",
        "confidence": 0.87,  # 置信度
        "affected_area_ratio": 0.15,  # 病斑面积占比 (15%)
        "bboxes": [  # 供前端在图片上画框的坐标
            {"xmin": 120, "ymin": 45, "xmax": 210, "ymax": 160, "label": "downy_mildew", "conf": 0.87}
        ]
    }

    return mock_yolo_result


# ==========================================
# 5. 状态与最新数据路由 (补齐文档拼图)
# ==========================================
@app.get("/api/device/latest")
async def get_latest_data(device_id: str = "sensairshuttle_001", db: Session = Depends(get_db)):
    """获取设备最新的一条完整遥测数据"""
    # 查询指定设备，按时间戳倒序排列，取出第一条 (first)
    record = db.query(models.TelemetryRecord).filter(
        models.TelemetryRecord.device_id == device_id
    ).order_by(models.TelemetryRecord.timestamp.desc()).first()

    if not record:
        return {"status": "error", "message": "暂无该设备数据"}
    return {"status": "success", "data": record}


@app.get("/api/device/status")
async def get_device_status(device_id: str = "sensairshuttle_001", db: Session = Depends(get_db)):
    """仅获取设备当前的网络在线状态与外设运行状态"""
    record = db.query(models.TelemetryRecord).filter(
        models.TelemetryRecord.device_id == device_id
    ).order_by(models.TelemetryRecord.timestamp.desc()).first()

    if not record:
        return {"status": "error", "message": "设备离线或无数据"}

    # 提取关键状态字段，组装返回
    return {
        "status": "success",
        "device_status": {
            "wifi": record.wifi_status,
            "mqtt": record.mqtt_status,
            "fan": record.fan_status,
            "pump": 0,  # 简化版数据库中暂未记录，占位供前端联调
            "light": 0  # 简化版数据库中暂未记录，占位供前端联调
        }
    }

@app.post("/api/ai/analyze")
async def analyze_ai(
    device_id: str = "sensairshuttle_001",
    crop: str = "tomato",
    db: Session = Depends(get_db)
):

    record = db.query(models.TelemetryRecord).filter(
        models.TelemetryRecord.device_id == device_id
    ).order_by(
        models.TelemetryRecord.timestamp.desc()
    ).first()

    if not record:
        return {
            "status": "error",
            "message": "暂无设备数据"
        }

    sensor_data = {
        "temperature": record.temperature,
        "humidity": record.humidity,
        "pressure": record.pressure,
        "gas_resistance": record.gas_resistance
    }

    prompt = build_prompt(
        sensor_data,
        AGRICULTURE_KB
    )

    result = chat(prompt)

    result = make_decision(
        result,
        sensor_data
    )

    return {
        "status": "success",
        "device_id": device_id,
        "crop": crop,
        **result
    }