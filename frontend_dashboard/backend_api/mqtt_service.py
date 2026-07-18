from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any

from database import SessionLocal
from device_models import DeviceCommandRecord
from device_schemas import CommandAckRequest, TelemetryInPayload
from device_service import acknowledge_command, claim_next_command, save_telemetry
from monitoring_service import update_device_connection_status
from site_service import (
    acknowledge_site_command,
    c5_device_id,
    claim_next_site_command,
    command_wire_payload,
    create_edge_assistant_reply,
    decide_edge_assistant_action,
    expire_site_commands,
    return_site_command_to_queue,
    s3_device_id,
    save_site_telemetry,
    update_edge_capabilities,
    update_edge_status,
)


logger = logging.getLogger("mqtt-transport")


def enabled() -> bool:
    return os.getenv("MQTT_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def mqtt_command_transport() -> bool:
    return os.getenv("DEVICE_COMMAND_TRANSPORT", "http").strip().lower() == "mqtt"


def canonical_telemetry(raw: dict[str, Any]) -> TelemetryInPayload:
    """Compatibility mapper for the existing /api/device contract and tests."""
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


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class MqttRuntime:
    def __init__(self) -> None:
        self._client: Any = None
        self._mqtt: Any = None
        self._connected = threading.Event()
        self._stop_event = threading.Event()
        self._command_thread: threading.Thread | None = None
        self._topic_prefix = "smartagribrain/v1"

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> None:
        if not enabled() or self._client is not None:
            return
        host = os.getenv("MQTT_HOST", "").strip()
        if not host:
            logger.warning("MQTT is enabled but MQTT_HOST is empty")
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt is not installed; HTTP endpoints remain available")
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
                logger.exception("Failed to stop MQTT runtime")
        self._client = None

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if getattr(reason_code, "is_failure", False):
            logger.warning("MQTT connection failed: %s", reason_code)
            return
        self._connected.set()
        qos = int(os.getenv("MQTT_QOS", "1"))
        base = f"{self._topic_prefix}/devices/+"
        for suffix in ("telemetry", "status", "capabilities", "command_ack", "assistant/request", "assistant/decision"):
            client.subscribe(f"{base}/{suffix}", qos=qos)

    def _on_disconnect(
        self,
        client: Any,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        self._connected.clear()
        if not self._stop_event.is_set():
            logger.warning("MQTT disconnected; automatic reconnect is active")

    def _parse_topic(self, topic: str) -> tuple[str, str]:
        marker = f"{self._topic_prefix}/devices/"
        if not topic.startswith(marker):
            raise ValueError("topic is outside configured prefix")
        parts = topic[len(marker) :].split("/", 1)
        if len(parts) != 2 or not all(parts):
            raise ValueError("invalid device topic")
        return parts[0], parts[1]

    def _publish_json(self, topic: str, payload: dict[str, Any], *, retain: bool = False) -> bool:
        if self._client is None:
            return False
        qos = int(os.getenv("MQTT_QOS", "1"))
        result = self._client.publish(
            topic,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            qos=qos,
            retain=retain,
        )
        return result.rc == self._mqtt.MQTT_ERR_SUCCESS

    def _publish_view_state(self, state: Any) -> None:
        self._publish_json(
            f"{self._topic_prefix}/devices/{c5_device_id()}/view_state",
            state.model_dump(mode="json"),
            retain=True,
        )

    def _publish_assistant_response(self, payload: dict[str, Any]) -> None:
        self._publish_json(
            f"{self._topic_prefix}/devices/{c5_device_id()}/assistant/response",
            payload,
            retain=False,
        )

    def _handle_assistant_message(self, raw: dict[str, Any], topic_device_id: str) -> None:
        try:
            if topic_device_id != c5_device_id():
                raise ValueError("assistant requests are only accepted from the configured C5")
            text = str(raw.get("text") or "").strip()
            if not text:
                raise ValueError("assistant request text is empty")
            site_id = str(raw.get("site_id") or os.getenv("DEFAULT_SITE_ID", "greenhouse_001"))
            with SessionLocal() as db:
                response = create_edge_assistant_reply(
                    db,
                    site_id,
                    text,
                    str(raw.get("session_id") or "") or None,
                    "edge_text",
                )
            # Keep the C5's compact local conversation in sync with the
            # backend-owned session without requiring the device to fetch it.
            self._publish_assistant_response({
                "kind": "assistant_turn",
                "session_id": response.session_id,
                "user_content": text,
                "assistant": response.model_dump(mode="json"),
            })
        except Exception as exc:
            logger.exception("Unable to process C5 assistant request")
            self._publish_assistant_response({"error": {"code": "ASSISTANT_ERROR", "message": str(exc)}})

    def _handle_assistant_decision(self, raw: dict[str, Any], topic_device_id: str) -> None:
        try:
            if topic_device_id != c5_device_id():
                raise ValueError("assistant decisions are only accepted from the configured C5")
            site_id = str(raw.get("site_id") or os.getenv("DEFAULT_SITE_ID", "greenhouse_001"))
            action_id = str(raw.get("action_id") or "")
            decision = str(raw.get("decision") or "")
            if decision not in {"confirm", "cancel"}:
                raise ValueError("decision must be confirm or cancel")
            with SessionLocal() as db:
                response = decide_edge_assistant_action(db, site_id, action_id, decision)
            self._publish_assistant_response({"kind": "action", **response.model_dump(mode="json")})
        except Exception as exc:
            logger.exception("Unable to process C5 assistant decision")
            self._publish_assistant_response({"error": {"code": "DECISION_ERROR", "message": str(exc)}})

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        try:
            raw = json.loads(message.payload.decode("utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("MQTT payload must be a JSON object")
            topic_device_id, suffix = self._parse_topic(message.topic)

            if suffix == "telemetry":
                if raw.get("site_id") is not None or topic_device_id == s3_device_id():
                    with SessionLocal() as db:
                        state = save_site_telemetry(db, raw, topic_device_id)
                    self._publish_view_state(state)
                else:
                    payload = canonical_telemetry(raw)
                    with SessionLocal() as db:
                        save_telemetry(db, payload, transport="mqtt")
                return

            if suffix == "status":
                if raw.get("site_id") is not None or topic_device_id in {s3_device_id(), c5_device_id()}:
                    with SessionLocal() as db:
                        state = update_edge_status(db, raw, topic_device_id)
                    self._publish_view_state(state)
                else:
                    online_value = raw.get("online")
                    online = online_value if isinstance(online_value, bool) else str(online_value).lower() in {
                        "1",
                        "true",
                        "online",
                    }
                    with SessionLocal() as db:
                        update_device_connection_status(db, topic_device_id, online, "mqtt")
                return

            if suffix == "capabilities":
                with SessionLocal() as db:
                    state = update_edge_capabilities(db, raw, topic_device_id)
                self._publish_view_state(state)
                return

            if suffix == "command_ack":
                if _is_uuid(raw.get("command_id")):
                    with SessionLocal() as db:
                        acknowledge_site_command(db, raw)
                    return
                command_id = int(raw.get("command_id"))
                succeeded = str(raw.get("state") or "").lower() in {"executed", "succeeded", "success"}
                message_text = str(raw.get("message") or ("device command completed" if succeeded else "device command failed"))
                with SessionLocal() as db:
                    acknowledge_command(db, command_id, CommandAckRequest(success=succeeded, message=message_text))
                return

            if suffix == "assistant/request":
                threading.Thread(
                    target=self._handle_assistant_message,
                    args=(raw, topic_device_id),
                    name="c5-assistant-request",
                    daemon=True,
                ).start()
                return

            if suffix == "assistant/decision":
                threading.Thread(
                    target=self._handle_assistant_decision,
                    args=(raw, topic_device_id),
                    name="c5-assistant-decision",
                    daemon=True,
                ).start()
        except Exception:
            logger.exception("Unable to process MQTT device message on %s", getattr(message, "topic", "unknown"))

    def _dispatch_site_command(self) -> bool:
        command_id: str | None = None
        try:
            with SessionLocal() as db:
                expire_site_commands(db)
                queued = claim_next_site_command(db)
                if queued is None:
                    return False
                command_id = queued.command_id
                topic = f"{self._topic_prefix}/devices/{queued.device_id}/command"
                if not self._publish_json(topic, command_wire_payload(queued)):
                    return_site_command_to_queue(db, queued.command_id)
            return True
        except Exception:
            logger.exception("Unable to dispatch site command; it will be retried until expiry")
            if command_id is not None:
                with SessionLocal() as db:
                    return_site_command_to_queue(db, command_id)
            return False

    def _dispatch_legacy_command(self) -> None:
        device_ids = [os.getenv("DEFAULT_DEVICE_ID", "sensairshuttle_001"), s3_device_id()]
        device_ids = list(dict.fromkeys(device_id for device_id in device_ids if device_id))
        queued_command_id: int | None = None
        try:
            with SessionLocal() as db:
                queued = None
                for device_id in device_ids:
                    queued = claim_next_command(db, device_id, consumer_transport="mqtt")
                    if queued is not None:
                        break
                if queued is None:
                    return
                queued_command_id = queued.command_id
                ttl_seconds = max(5, int(os.getenv("MQTT_COMMAND_TTL_SECONDS", "30")))
                if queued.created_at + ttl_seconds * 1000 < int(time.time() * 1000):
                    acknowledge_command(
                        db,
                        queued.command_id,
                        CommandAckRequest(success=False, message="command expired before delivery"),
                    )
                    return
                body = {
                    "schema_version": "1.0",
                    "command_id": str(queued.command_id),
                    "device_id": queued.device_id,
                    "issued_at": queued.created_at,
                    "expires_at": queued.created_at + ttl_seconds * 1000,
                    "source": "web_manual",
                    "reason": queued.reason,
                    "command": {
                        "operation": "target_position" if queued.command == "target_position" else "set",
                        "target": "position" if queued.command == "target_position" else command_target(queued.command),
                        "value": queued.value,
                    },
                }
                if queued.command == "target_position":
                    position = queued.payload.get("position") if isinstance(queued.payload, dict) else None
                    if isinstance(position, dict):
                        body["command"]["position"] = position
                    water_gun = queued.payload.get("water_gun") if isinstance(queued.payload, dict) else None
                    if isinstance(water_gun, dict):
                        body["command"]["water_gun"] = water_gun
                if not self._publish_json(f"{self._topic_prefix}/devices/{queued.device_id}/command", body):
                    record = db.get(DeviceCommandRecord, queued.command_id)
                    if record is not None and record.status == "dispatched":
                        record.status = "queued"
                        record.dispatched_at = None
                        db.commit()
        except Exception:
            logger.exception("Unable to dispatch legacy device command")
            if queued_command_id is not None:
                with SessionLocal() as db:
                    record = db.get(DeviceCommandRecord, queued_command_id)
                    if record is not None and record.status == "dispatched":
                        record.status = "queued"
                        record.dispatched_at = None
                        db.commit()

    def _command_loop(self) -> None:
        while not self._stop_event.wait(0.05):
            if not self._connected.is_set() or self._client is None:
                continue
            dispatched = self._dispatch_site_command()
            if mqtt_command_transport():
                self._dispatch_legacy_command()
            if dispatched:
                time.sleep(0.05)


mqtt_runtime = MqttRuntime()
