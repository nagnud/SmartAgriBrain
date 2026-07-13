import json
import logging
import time
import uuid
from threading import Thread
import paho.mqtt.client as mqtt
import ulid

# 引入数据库与模型
from database import SessionLocal
import models

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MQTT_Bridge")

# ================= 契约第 8 节：配置标准 =================
MQTT_URI = "broker.emqx.io"  # 联调时暂用公共Broker，后续切为你们的真实地址
MQTT_PORT = 1883
MQTT_CLIENT_ID = f"sab-api-{uuid.uuid4().hex[:8]}" # 后端 Client ID 契约
MQTT_TOPIC_PREFIX = "smartagribrain/v1" # 统一主题前缀
# =======================================================


def on_connect(client, userdata, flags, rc):
    """MQTT 连接成功后的回调函数"""
    if rc == 0:
        logger.info(f"✅ 成功连接到 MQTT Broker: {MQTT_URI}")
        # 契约 3.2: 后端必须以通配符 + 订阅所有设备的 4 个核心主题
        base_topic = f"{MQTT_TOPIC_PREFIX}/devices/+"
        client.subscribe(f"{base_topic}/telemetry", qos=1)
        client.subscribe(f"{base_topic}/status", qos=1)
        client.subscribe(f"{base_topic}/capabilities", qos=1)
        client.subscribe(f"{base_topic}/command_ack", qos=1)
        logger.info(f"📡 已按 V1 契约开启全量设备主题监听: {base_topic}/#")
    else:
        logger.error(f"❌ MQTT 连接失败，返回码: {rc}")


def on_message(client, userdata, msg):
    """MQTT 接收报文的统一路由与数据入库中枢"""
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        topic = msg.topic

        # ==========================================
        # 1. 契约 3.4: 处理遥测数据入库
        # ==========================================
        if topic.endswith("/telemetry"):
            db = SessionLocal()
            try:
                record_id = ulid.new().str
                # 检查 message_id 是否已存在，保证幂等去重
                existing = (
                    db.query(models.Telemetry)
                    .filter(models.Telemetry.message_id == payload.get("message_id"))
                    .first()
                )
                if not existing:
                    sensors = payload.get("sensors", {})
                    telemetry_record = models.Telemetry(
                        record_id=record_id,
                        message_id=payload.get("message_id"),
                        device_id=payload.get("device_id"),
                        sequence=payload.get("sequence"),
                        sampled_at=payload.get("sampled_at"),
                        received_at=int(time.time() * 1000), # 服务端标记接收时间
                        # 物理精度字段严格对齐契约
                        temperature_c=sensors.get("temperature_c"),
                        humidity_pct=sensors.get("humidity_pct"),
                        pressure_kpa=sensors.get("pressure_kpa"),
                        gas_resistance_ohm=sensors.get("gas_resistance_ohm"),
                        illuminance_lux=sensors.get("illuminance_lux"),
                        co2_ppm=sensors.get("co2_ppm"),
                        soil_moisture_pct=sensors.get("soil_moisture_pct"),
                        soil_ec_ms_cm=sensors.get("soil_ec_ms_cm"),
                        # 保留完整未扁平化的 JSON 快照
                        payload_snapshot=payload,
                    )
                    db.add(telemetry_record)
                    db.commit()
                    logger.info(f"💾 [遥测入库成功] 设备: {payload.get('device_id')} | Record ID: {record_id}")
            except Exception as db_e:
                db.rollback()
                logger.error(f"❌ 遥测数据入库失败: {db_e}")
            finally:
                db.close()

        # ==========================================
        # 2. 契约 3.5: 处理在线状态 (status/LWT)
        # ==========================================
        elif topic.endswith("/status"):
            logger.info(f"🟢 [状态变更] 设备 {payload.get('device_id')} 在线状态: {payload.get('online')}")
            db = SessionLocal()
            try:
                dev_id = payload.get("device_id")
                status_record = models.DeviceStatus(
                    device_id=dev_id,
                    online=payload.get("online", False),
                    last_seen_at=payload.get("reported_at", int(time.time() * 1000)),
                )
                db.merge(status_record)
                db.commit()
            except Exception as db_e:
                db.rollback()
                logger.error(f"❌ 状态更新失败: {db_e}")
            finally:
                db.close()

        # ==========================================
        # 3. 契约 3.3: 处理设备能力声明
        # ==========================================
        elif topic.endswith("/capabilities"):
            logger.info(f"📋 [能力上报] 设备 {payload.get('device_id')} 固件版本: {payload.get('firmware', {}).get('version')}")
            # 已成功日志监听，表更新可在联调后期补充

        # ==========================================
        # 4. 契约 3.6: 指令回执入库与状态机翻转
        # ==========================================
        elif topic.endswith("/command_ack"):
            logger.info(f"🎯 [命令确认] 命令 {payload.get('command_id')} 状态: {payload.get('state')}")
            db = SessionLocal()
            try:
                cmd_id = payload.get("command_id")
                ack_state = payload.get("state")  # executed 或 rejected

                # 写入 CommandAck 附表记录
                ack_record = models.CommandAck(
                    command_id=cmd_id,
                    device_id=payload.get("device_id"),
                    acknowledged_at=payload.get("acknowledged_at", int(time.time() * 1000)),
                    state=ack_state,
                    actual_value=payload.get("actual_value"),
                    error_code=payload.get("error", {}).get("code") if payload.get("error") else None,
                    full_payload=payload,
                )
                db.merge(ack_record)

                # 同步更新主命令表的状态 PUBLISHED -> EXECUTED / REJECTED
                cmd = db.query(models.Command).filter(models.Command.command_id == cmd_id).first()
                if cmd:
                    cmd.state = "EXECUTED" if ack_state == "executed" else "REJECTED" #
                    cmd.completed_at = int(time.time() * 1000)

                db.commit()
                logger.info(f"🎯 [指令闭环成功] 命令ID: {cmd_id} | 最终状态: {cmd.state if cmd else ack_state}")
            except Exception as db_e:
                db.rollback()
                logger.error(f"❌ ACK 入库失败: {db_e}")
            finally:
                db.close()

    except Exception as e:
        logger.error(f"⚠️ 解析 MQTT 消息异常: {e} | Payload: {msg.payload}")


# 初始化客户端实例
# 初始化客户端实例（显式指定 CallbackAPIVersion.VERSION1 以兼容原有回调签名）
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1, client_id=MQTT_CLIENT_ID)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message


def start_mqtt_loop():
    """建立阻塞循环（需在独立线程运行）"""
    try:
        mqtt_client.connect(MQTT_URI, MQTT_PORT, 60)
        mqtt_client.loop_forever()
    except Exception as e:
        logger.error(f"🚨 MQTT 启动失败: {e}")


def start_mqtt_background():
    """在后台挂起 MQTT 客户端，防止阻塞 FastAPI 的 HTTP 进程"""
    thread = Thread(target=start_mqtt_loop, daemon=True)
    thread.start()


def publish_command(device_id: str, target: str, value: int, source: str = "web_manual", reason: str = "用户手动控制"):
    """
    契约 3.6 & 4.4: 标准化命令下发
    严格包含 command_id, expires_at 等必要控制属性
    """
    command_id = str(uuid.uuid4())
    issued_at = int(time.time() * 1000)
    expires_at = issued_at + 30000  # 默认 30 秒超时

    command_payload = {
        "schema_version": "1.0",
        "command_id": command_id,
        "device_id": device_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "source": source,
        "reason": reason,
        "command": {
            "operation": "set",
            "target": target,
            "value": value
        }
    }

    topic = f"{MQTT_TOPIC_PREFIX}/devices/{device_id}/command" # 动态下发至目标设备主题
    msg_str = json.dumps(command_payload)
    mqtt_client.publish(topic, msg_str, qos=1) #
    logger.info(f"📤 [命令下发] 状态: PUBLISHED | 目标: {device_id} | 执行器: {target}={value}")

    return command_payload