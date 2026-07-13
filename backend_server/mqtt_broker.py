import json
import logging
import paho.mqtt.client as mqtt
from threading import Thread
# 在 mqtt_broker.py 顶部追加导入
from database import SessionLocal
import models
import ulid # 终端执行 pip install ulid-py
import time
# 日志配置，方便你在终端监控硬件通信状态
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MQTT_Bridge")

# ================= 配置区 =================
# TODO: 联调时，请将这里换成你们团队自己的 EMQX 服务器 IP 或阿里云地址
MQTT_BROKER = "broker.emqx.io"  # 暂用免费公共测试 Broker
MQTT_PORT = 1883
MQTT_CLIENT_ID = "SmartAgri_Cloud_Backend_001"

# 约定通信契约 (Topic)
TOPIC_TELEMETRY = "smartagri/device/telemetry" # 订阅：ESP32 往云端发数据
TOPIC_COMMAND = "smartagri/device/command"     # 发布：云端往 ESP32 发指令
# =========================================

def on_connect(client, userdata, flags, rc):
    """MQTT 连接成功后的回调函数"""
    if rc == 0:
        logger.info(f"✅ 成功连接到 MQTT Broker: {MQTT_BROKER}")
        # 连接成功后，立刻开启监听硬件上传数据的通道
        client.subscribe(TOPIC_TELEMETRY)
        logger.info(f"📡 已开启硬件遥测通道监听: {TOPIC_TELEMETRY}")
    else:
        logger.error(f"❌ MQTT 连接失败，返回码: {rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
        topic = msg.topic

        # 契约 3.4: 处理遥测数据入库
        if topic.endswith("/telemetry"):
            db = SessionLocal()
            try:
                # 生成 ULID 作为 record_id
                record_id = ulid.new().str
                # 检查 message_id 是否已存在 (幂等性去重)
                existing = db.query(models.Telemetry).filter(
                    models.Telemetry.message_id == payload.get("message_id")).first()
                if not existing:
                    sensors = payload.get("sensors", {})
                    telemetry_record = models.Telemetry(
                        record_id=record_id,
                        message_id=payload.get("message_id"),
                        device_id=payload.get("device_id"),
                        sequence=payload.get("sequence"),
                        sampled_at=payload.get("sampled_at"),
                        received_at=int(time.time() * 1000),
                        # 字段精准对齐契约
                        temperature_c=sensors.get("temperature_c"),
                        humidity_pct=sensors.get("humidity_pct"),
                        pressure_kpa=sensors.get("pressure_kpa"),
                        gas_resistance_ohm=sensors.get("gas_resistance_ohm"),
                        illuminance_lux=sensors.get("illuminance_lux"),
                        co2_ppm=sensors.get("co2_ppm"),
                        soil_moisture_pct=sensors.get("soil_moisture_pct"),
                        soil_ec_ms_cm=sensors.get("soil_ec_ms_cm"),
                        # 保留完整快照
                        payload_snapshot=payload
                    )
                    db.add(telemetry_record)
                    db.commit()
                    logger.info(f"💾 [遥测入库成功] 设备: {payload.get('device_id')} | Record ID: {record_id}")
            except Exception as db_e:
                db.rollback()
                logger.error(f"❌ 数据入库失败: {db_e}")
            finally:
                db.close()

        # 契约 3.5: 状态变更
        elif topic.endswith("/status"):
            logger.info(f"🟢 [状态变更] 设备 {payload.get('device_id')} 在线状态: {payload.get('online')}")
            # TODO: 后续补全 device_status 表更新逻辑

        # 契约 3.3: 设备能力
        elif topic.endswith("/capabilities"):
            logger.info(
                f"📋 [能力上报] 设备 {payload.get('device_id')} 固件版本: {payload.get('firmware', {}).get('version')}")
            # TODO: 后续补全 device_capabilities 表更新逻辑

        # 契约 3.6: 指令回执
        elif topic.endswith("/command_ack"):
            logger.info(f"🎯 [命令确认] 命令 {payload.get('command_id')} 状态: {payload.get('state')}")
            # TODO: 后续补全 commands 表流转状态更新逻辑

    # 这个就是你截图里缺失的、用来闭合最外层 try 的 except
    except Exception as e:
        logger.error(f"⚠️ 解析 MQTT 消息失败: {e} | Payload: {msg.payload}")

# 初始化客户端实例
mqtt_client = mqtt.Client(MQTT_CLIENT_ID)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def start_mqtt_loop():
    """建立阻塞循环（需在独立线程运行）"""
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_forever()
    except Exception as e:
        logger.error(f"🚨 MQTT 启动失败: {e}")

def start_mqtt_background():
    """在后台挂起 MQTT 客户端，防止阻塞 FastAPI 的 HTTP 进程"""
    thread = Thread(target=start_mqtt_loop, daemon=True)
    thread.start()

def publish_command(target: str, action: int):
    """
    HTTP 接口 / AI 引擎专属调用入口
    将逻辑指令转换为 JSON，通过 MQTT 下发给 ESP32
    """
    command_payload = {
        "target": target,  # 例如: "fan" (风机), "pump" (水泵)
        "action": action   # 例如: 1 (开), 0 (关)
    }
    msg_str = json.dumps(command_payload)
    mqtt_client.publish(TOPIC_COMMAND, msg_str)
    logger.info(f"📤 已向 ESP32 下发控制指令: {msg_str} -> {TOPIC_COMMAND}")