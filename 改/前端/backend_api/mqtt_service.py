from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any
from urllib.parse import urlsplit

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
    get_edge_conversation,
    now_ms,
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
    """Return whether the only supported device-command transport is active.

    MQTT is the project default.  A local HTTP pull queue is retained only when
    a developer deliberately sets ``DEVICE_COMMAND_TRANSPORT=http`` for a
    compatibility test; it must never become the implicit real-device path.
    """
    return os.getenv("DEVICE_COMMAND_TRANSPORT", "mqtt").strip().lower() == "mqtt"


def mqtt_endpoint() -> tuple[str, int, bool] | None:
    """Read the only supported Broker endpoint: an externally managed EMQX URI.

    Keeping the protocol in one value prevents the old local ``MQTT_HOST`` plus
    ``MQTT_PORT`` settings from silently reconnecting the API to Mosquitto.
    ``mqtts`` selects TLS and defaults to 8883; ``mqtt`` is available only for
    an explicitly configured non-TLS EMQX listener.
    """
    raw_uri = os.getenv("MQTT_URI", "").strip()
    if not raw_uri:
        return None
    parsed = urlsplit(raw_uri)
    if parsed.scheme not in {"mqtt", "mqtts"} or not parsed.hostname:
        raise ValueError("MQTT_URI must be mqtts://host:8883 or mqtt://host:1883")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("MQTT_URI must only contain scheme, host and optional port")
    use_tls = parsed.scheme == "mqtts"
    port = parsed.port or (8883 if use_tls else 1883)
    if use_tls and port != 8883:
        raise ValueError("MQTT_URI must use the MQTT TLS port 8883")
    if not use_tls and port != 1883:
        raise ValueError("MQTT_URI must use the non-TLS MQTT port 1883")
    return parsed.hostname, port, use_tls


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
        try:
            endpoint = mqtt_endpoint()
        except ValueError as error:
            logger.warning("MQTT is enabled but EMQX configuration is invalid: %s", error)
            return
        if endpoint is None:
            logger.warning("MQTT is enabled but MQTT_URI is empty; local Mosquitto is not supported")
            return
        host, port, use_tls = endpoint
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt is not installed; HTTP endpoints remain available")
            return

        self._mqtt = mqtt
        self._topic_prefix = os.getenv("MQTT_TOPIC_PREFIX", "smartagribrain/v1").strip().strip("/")
        client_id = os.getenv("MQTT_CLIENT_ID", "smartagribrain-api").strip()
        if not client_id:
            logger.warning("MQTT_CLIENT_ID must be non-empty when using a persistent EMQX session")
            return
        # A stable ID plus clean_session=False lets EMQX retain QoS 1 state
        # across a FastAPI process restart. Command payloads still carry TTLs
        # and idempotency keys, so a resumed session cannot safely replay work.
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=False,
        )
        username = os.getenv("MQTT_USERNAME", "").strip()
        if username:
            self._client.username_pw_set(username, os.getenv("MQTT_PASSWORD", ""))
        configured_tls = os.getenv("MQTT_TLS", "").strip().lower()
        if configured_tls and (configured_tls in {"1", "true", "yes", "on"}) != use_tls:
            logger.warning("MQTT_TLS conflicts with MQTT_URI scheme; using MQTT_URI")
        if use_tls:
            self._client.tls_set(ca_certs=os.getenv("MQTT_CA_CERT") or None)
            if os.getenv("MQTT_TLS_INSECURE", "false").strip().lower() in {"1", "true", "yes", "on"}:
                logger.warning("MQTT_TLS_INSECURE is enabled; certificate hostname verification is disabled")
                self._client.tls_insecure_set(True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.enable_logger(logger)
        keepalive = int(os.getenv("MQTT_KEEPALIVE_SECONDS", "60"))
        logger.info("Connecting to external EMQX Broker host=%s port=%s tls=%s", host, port, use_tls)
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
        for suffix in (
            "telemetry",
            "status",
            "capabilities",
            "command_ack",
            "assistant/request",
            "assistant/decision",
            "assistant/recover",
        ):
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

    def _publish_assistant_clear(self, *, session_id: str, content: str = "", recovered: bool = False) -> None:
        payload: dict[str, Any] = {
            "kind": "voice_control",
            "session_id": session_id,
            "assistant": {
                "content": content,
                "actions": [],
                "next_input": "none",
            },
        }
        if recovered:
            payload["recovered"] = True
        self._publish_assistant_response(payload)

    @staticmethod
    def _pending_actions(actions: Any, *, current_ms: int | None = None) -> list[dict[str, Any]]:
        if not isinstance(actions, list):
            return []
        timestamp = now_ms() if current_ms is None else current_ms
        pending: list[dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, dict) or action.get("state") != "pending":
                continue
            try:
                expires_at = int(action.get("expires_at") or 0)
            except (TypeError, ValueError):
                continue
            if expires_at >= timestamp:
                pending.append(action)
        return pending

    def publish_voice_control(
        self,
        *,
        answer: str,
        actions: Any,
        session_id: str,
        user_content: str = "",
        turn_id: str | None = None,
        next_input: str = "none",
    ) -> bool:
        """Deliver pending voice actions independently from streamed audio."""
        pending = self._pending_actions(actions)
        resolved_next_input = next_input if next_input in {"none", "duration", "confirmation", "parameter"} else "none"
        if pending and resolved_next_input == "none":
            resolved_next_input = "confirmation"
        payload: dict[str, Any] = {
            "kind": "voice_control",
            "session_id": session_id,
            "user_content": user_content,
            "assistant": {
                "content": answer,
                "actions": pending,
                "next_input": resolved_next_input,
            },
        }
        if turn_id:
            payload["turn_id"] = turn_id
        return self._publish_json(
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
            session_id = str(raw.get("session_id") or "")
            if decision not in {"confirm", "cancel"}:
                raise ValueError("decision must be confirm or cancel")
            with SessionLocal() as db:
                response = decide_edge_assistant_action(db, site_id, action_id, decision)
            self._publish_assistant_response({"kind": "action", **response.model_dump(mode="json")})
            self._publish_assistant_clear(session_id=session_id, content=str(response.payload.get("error") or ""))
        except Exception as exc:
            logger.exception("Unable to process C5 assistant decision")
            code = "NO_PENDING_ACTION" if isinstance(exc, LookupError) else "DECISION_ERROR"
            self._publish_assistant_response({
                "kind": "voice_control",
                "assistant": {
                    "content": "当前没有待确认操作" if code == "NO_PENDING_ACTION" else "",
                    "actions": [],
                    "next_input": "none",
                },
                "error": {"code": code, "message": str(exc)},
            })

    def _handle_assistant_recovery(self, raw: dict[str, Any], topic_device_id: str) -> None:
        """Restore a still-pending action after the C5 reconnects."""
        try:
            if topic_device_id != c5_device_id():
                raise ValueError("assistant recovery is only accepted from the configured C5")
            site_id = str(raw.get("site_id") or os.getenv("DEFAULT_SITE_ID", "greenhouse_001"))
            requested_session = str(raw.get("session_id") or "").strip() or None
            with SessionLocal() as db:
                conversation = get_edge_conversation(db, site_id, requested_session)
                if requested_session is not None:
                    latest_conversation = get_edge_conversation(db, site_id, None)
                    requested_updated_at = conversation.messages[-1].created_at if conversation.messages else 0
                    latest_updated_at = latest_conversation.messages[-1].created_at if latest_conversation.messages else 0
                    if latest_updated_at > requested_updated_at:
                        conversation = latest_conversation

            recovered_message: Any = None
            recovered_actions: list[dict[str, Any]] = []
            timestamp = now_ms()
            for message in reversed(conversation.messages):
                if message.role != "assistant":
                    continue
                recovered_message = message
                candidate_actions = self._pending_actions(
                    [action.model_dump(mode="json") for action in message.actions],
                    current_ms=timestamp,
                )
                if candidate_actions:
                    recovered_actions = candidate_actions
                break

            self._publish_assistant_response({
                "kind": "voice_control",
                "recovered": True,
                "session_id": conversation.session_id or requested_session or "",
                "assistant": {
                    "content": recovered_message.content if recovered_message is not None else "",
                    "actions": recovered_actions,
                    "next_input": "confirmation" if recovered_actions else "none",
                },
            })
            if recovered_actions:
                logger.info("Recovered pending C5 assistant action for session %s", conversation.session_id)
        except Exception as exc:
            logger.exception("Unable to recover C5 assistant action")
            self._publish_assistant_response({"error": {"code": "RECOVERY_ERROR", "message": str(exc)}})

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
                # Compact ACKs no longer duplicate a top-level message. For a
                # rejection, preserve the device error code in the legacy
                # command record instead of replacing it with generic text.
                error = raw.get("error") if isinstance(raw.get("error"), dict) else {}
                default_message = "device command completed" if succeeded else str(
                    error.get("code") or "device command failed"
                )
                message_text = str(raw.get("message") or default_message)
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
                return

            if suffix == "assistant/recover":
                threading.Thread(
                    target=self._handle_assistant_recovery,
                    args=(raw, topic_device_id),
                    name="c5-assistant-recovery",
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
        device_ids = [os.getenv("DEFAULT_DEVICE_ID", "greenhouse_001_s3"), s3_device_id()]
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
                # The v1 Topic identifies both protocol and device. Keep only
                # fields the ESP32 needs to expire, deduplicate, and execute
                # the command; audit metadata remains in DeviceCommandRecord.
                body = {
                    "command_id": str(queued.command_id),
                    "expires_at": queued.created_at + ttl_seconds * 1000,
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
