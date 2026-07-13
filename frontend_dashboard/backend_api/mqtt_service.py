from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from database import SessionLocal
from device_models import DeviceCommandRecord
from device_schemas import CommandAckRequest, TelemetryInPayload
from device_service import acknowledge_command, claim_next_command, save_telemetry
from monitoring_service import update_device_connection_status


logger = logging.getLogger("mqtt-transport")


def enabled() -> bool:
    return os.getenv("MQTT_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def mqtt_command_transport() -> bool:
    return os.getenv("DEVICE_COMMAND_TRANSPORT", "http").strip().lower() == "mqtt"


def canonical_telemetry(raw: dict[str, Any]) -> TelemetryInPayload:
    sensors = raw.get("sensors") if isinstance(raw.get("sensors"), dict) else {}
    status = raw.get("status") if isinstance(raw.get("status"), dict) else None
    if "temperature" in sensors:
        payload = {
            "device_id": raw.get("device_id"),
            "timestamp": raw.get("timestamp") or raw.get("sampled_at"),
            "message_id": raw.get("message_id"),
            "sequence": raw.get("sequence"),
            "sensors": sensors,
            "status": status or {},
        }
        return TelemetryInPayload.model_validate(payload)

    connectivity = raw.get("connectivity") if isinstance(raw.get("connectivity"), dict) else {}
    actuators = raw.get("actuators") if isinstance(raw.get("actuators"), dict) else {}
    payload = {
        "device_id": raw.get("device_id"),
        "timestamp": raw.get("sampled_at") or raw.get("timestamp"),
        "message_id": raw.get("message_id"),
        "sequence": raw.get("sequence"),
        "sensors": {
            "temperature": sensors.get("temperature_c"),
            "humidity": sensors.get("humidity_pct"),
            "pressure": sensors.get("pressure_kpa"),
            "gas_resistance": sensors.get("gas_resistance_ohm"),
            "light": sensors.get("illuminance_lux"),
            "co2": sensors.get("co2_ppm"),
            "soil_moisture": sensors.get("soil_moisture_pct"),
            "soil_ec": sensors.get("soil_ec_ms_cm"),
        },
        "status": {
            "wifi": connectivity.get("wifi"),
            "mqtt": connectivity.get("mqtt", "connected"),
            "fan": actuators.get("fan"),
            "pump": actuators.get("pump"),
            "light": actuators.get("light"),
            "alarm": actuators.get("alarm"),
            "curtain": actuators.get("curtain"),
        },
    }
    return TelemetryInPayload.model_validate(payload)


def command_target(command: str) -> str:
    if command.startswith("curtain_"):
        return "curtain"
    return command.rsplit("_", 1)[0]


class MqttRuntime:
    def __init__(self) -> None:
        self._client: Any = None
        self._mqtt: Any = None
        self._connected = threading.Event()
        self._stop_event = threading.Event()
        self._command_thread: threading.Thread | None = None
        self._topic_prefix = "smartagribrain/v1"

    def start(self) -> None:
        if not enabled() or self._client is not None:
            return
        host = os.getenv("MQTT_HOST", "").strip()
        if not host:
            logger.warning("云端消息服务已启用，但尚未配置服务器地址")
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("云端消息服务依赖尚未安装，现有网页和设备接口不受影响")
            return

        self._mqtt = mqtt
        self._topic_prefix = os.getenv("MQTT_TOPIC_PREFIX", "smartagribrain/v1").strip().strip("/")
        client_id = os.getenv("MQTT_CLIENT_ID", f"smartagribrain-api-{os.getpid()}").strip()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        username = os.getenv("MQTT_USERNAME", "").strip()
        if username:
            self._client.username_pw_set(username, os.getenv("MQTT_PASSWORD", ""))
        if os.getenv("MQTT_TLS", "false").strip().lower() in {"1", "true", "yes", "on"}:
            self._client.tls_set(ca_certs=os.getenv("MQTT_CA_CERT") or None)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.enable_logger(logger)
        port = int(os.getenv("MQTT_PORT", "1883"))
        keepalive = int(os.getenv("MQTT_KEEPALIVE_SECONDS", "60"))
        self._stop_event.clear()
        self._client.connect_async(host, port, keepalive)
        self._client.loop_start()
        if mqtt_command_transport():
            self._command_thread = threading.Thread(target=self._command_loop, name="mqtt-command-dispatch", daemon=True)
            self._command_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._connected.clear()
        if self._command_thread is not None:
            self._command_thread.join(timeout=2)
            self._command_thread = None
        if self._client is not None:
            try:
                self._client.disconnect()
                self._client.loop_stop()
            except Exception:
                logger.exception("停止云端消息服务时出现异常")
        self._client = None

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if getattr(reason_code, "is_failure", False):
            logger.warning("云端消息服务暂时无法连接，正在自动重试")
            return
        self._connected.set()
        qos = int(os.getenv("MQTT_QOS", "1"))
        base = f"{self._topic_prefix}/devices/+"
        client.subscribe(f"{base}/telemetry", qos=qos)
        client.subscribe(f"{base}/status", qos=qos)
        client.subscribe(f"{base}/command_ack", qos=qos)

    def _on_disconnect(self, client: Any, userdata: Any, disconnect_flags: Any, reason_code: Any, properties: Any) -> None:
        self._connected.clear()
        if not self._stop_event.is_set():
            logger.warning("云端连接暂时中断，正在恢复")

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        try:
            raw = json.loads(message.payload.decode("utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("消息内容格式不正确")
            topic = message.topic
            if topic.endswith("/telemetry"):
                payload = canonical_telemetry(raw)
                with SessionLocal() as db:
                    save_telemetry(db, payload, transport="mqtt")
                return
            if topic.endswith("/status"):
                device_id = str(raw.get("device_id") or "").strip()
                if not device_id:
                    raise ValueError("缺少设备编号")
                online_value = raw.get("online")
                online = online_value if isinstance(online_value, bool) else str(online_value).lower() in {"1", "true", "online"}
                with SessionLocal() as db:
                    update_device_connection_status(db, device_id, online, "mqtt")
                return
            if topic.endswith("/command_ack"):
                command_id = int(raw.get("command_id"))
                succeeded = str(raw.get("state") or "").lower() in {"executed", "succeeded", "success"}
                message_text = str(raw.get("message") or ("设备已完成操作" if succeeded else "设备未能完成操作"))
                with SessionLocal() as db:
                    acknowledge_command(db, command_id, CommandAckRequest(success=succeeded, message=message_text))
        except Exception:
            logger.exception("收到一条无法处理的设备消息")

    def _command_loop(self) -> None:
        while not self._stop_event.wait(1):
            if not self._connected.is_set() or self._client is None:
                continue
            device_id = os.getenv("DEFAULT_DEVICE_ID", "sensairshuttle_001")
            queued_command_id: int | None = None
            try:
                with SessionLocal() as db:
                    queued = claim_next_command(db, device_id, consumer_transport="mqtt")
                    if queued is None:
                        continue
                    queued_command_id = queued.command_id
                    ttl_seconds = max(5, int(os.getenv("MQTT_COMMAND_TTL_SECONDS", "30")))
                    if queued.created_at + ttl_seconds * 1000 < int(time.time() * 1000):
                        acknowledge_command(
                            db,
                            queued.command_id,
                            CommandAckRequest(success=False, message="指令等待时间过长，请重新操作"),
                        )
                        continue
                    body = {
                        "schema_version": "1.0",
                        "command_id": str(queued.command_id),
                        "device_id": queued.device_id,
                        "issued_at": queued.created_at,
                        "expires_at": queued.created_at + ttl_seconds * 1000,
                        "source": "web_manual",
                        "reason": queued.reason,
                        "command": {
                            "operation": "set",
                            "target": command_target(queued.command),
                            "value": queued.value,
                        },
                    }
                    qos = int(os.getenv("MQTT_QOS", "1"))
                    result = self._client.publish(
                        f"{self._topic_prefix}/devices/{queued.device_id}/command",
                        json.dumps(body, ensure_ascii=False),
                        qos=qos,
                    )
                    if result.rc != self._mqtt.MQTT_ERR_SUCCESS:
                        record = db.get(DeviceCommandRecord, queued.command_id)
                        if record is not None and record.status == "dispatched":
                            record.status = "queued"
                            record.dispatched_at = None
                            db.commit()
            except Exception:
                logger.exception("设备操作暂时无法发送，将继续重试")
                if queued_command_id is not None:
                    try:
                        with SessionLocal() as db:
                            record = db.get(DeviceCommandRecord, queued_command_id)
                            if record is not None and record.status == "dispatched":
                                record.status = "queued"
                                record.dispatched_at = None
                                db.commit()
                    except Exception:
                        logger.exception("设备操作返回待发送队列时出现异常")


mqtt_runtime = MqttRuntime()
