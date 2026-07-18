from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(TEMP_DIR.name) / 'device-test.db').as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from app_state_models import AppState  # noqa: E402
from app_state_service import save_app_state_value  # noqa: E402
from database import SessionLocal, engine  # noqa: E402
from device_models import DeviceCommandRecord, TelemetryRecord  # noqa: E402
from main import app  # noqa: E402
from monitoring_models import (  # noqa: E402
    AlarmRecord,
    AlarmRuleState,
    DeviceAlarmSetting,
    DevicePresence,
    TelemetryReceipt,
)
from monitoring_service import check_offline_devices  # noqa: E402
from monitoring_service import DEFAULT_ALARM_RANGES, direction_for  # noqa: E402
from mqtt_service import canonical_telemetry  # noqa: E402
from mqtt_service import MqttRuntime  # noqa: E402
from kb_models import KnowledgeBase, KnowledgeItem  # noqa: E402
from kb_service import REFERENCE_TOMATO_BASE, seed_reference_tomato_knowledge  # noqa: E402
from region_service import search_region_options  # noqa: E402
from site_events import site_event_bus  # noqa: E402
from site_models import (  # noqa: E402
    EdgeAssistantAction,
    EdgeAssistantMessage,
    EdgeAssistantSession,
    EdgeDeviceRecord,
    SiteCommandRecord,
    SiteHistorySample,
    SiteSnapshotRecord,
)
from site_schemas import SiteCommandRequest  # noqa: E402
from site_service import (  # noqa: E402
    acknowledge_site_command,
    claim_next_site_command,
    command_wire_payload,
    create_edge_assistant_reply,
    decide_edge_assistant_action,
    expire_site_commands,
    normalize_site_telemetry,
    queue_site_command,
    save_site_telemetry,
    now_ms,
)
from assistant_orchestrator import _execute_tool, _is_camera_configuration_request, run_assistant_turn  # noqa: E402
from schemas import AssistantTurnRequest, PositionCandidate  # noqa: E402
from position_service import _remember  # noqa: E402
from water_gun_service import water_gun_runtime  # noqa: E402


def telemetry(device_id: str, timestamp: int, temperature: float = 26.5) -> dict:
    return {
        "device_id": device_id,
        "timestamp": timestamp,
        "sensors": {
            "temperature": temperature,
            "humidity": 62.3,
            "pressure": 101.2,
            "gas_resistance": 15800,
            "light": 18000,
            "co2": 650,
            "soil_moisture": 58.5,
            "soil_ec": 1.8,
        },
        "status": {
            "wifi": "connected",
            "mqtt": "connected",
            "fan": 0,
            "pump": 0,
            "light": 0,
            "alarm": 0,
            "curtain": 1,
        },
    }


class DeviceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Unit tests must never attach to the developer's real broker.
        os.environ["MQTT_ENABLED"] = "false"
        os.environ["DEVICE_COMMAND_TRANSPORT"] = "http"
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        engine.dispose()
        TEMP_DIR.cleanup()

    def setUp(self) -> None:
        with water_gun_runtime._lock:
            water_gun_runtime._states.clear()
        with SessionLocal() as db:
            db.query(AppState).delete()
            db.query(EdgeAssistantAction).delete()
            db.query(EdgeAssistantMessage).delete()
            db.query(EdgeAssistantSession).delete()
            db.query(SiteCommandRecord).delete()
            db.query(SiteHistorySample).delete()
            db.query(SiteSnapshotRecord).delete()
            db.query(EdgeDeviceRecord).delete()
            db.query(AlarmRuleState).delete()
            db.query(AlarmRecord).delete()
            db.query(DeviceAlarmSetting).delete()
            db.query(TelemetryReceipt).delete()
            db.query(DevicePresence).delete()
            db.query(DeviceCommandRecord).delete()
            db.query(TelemetryRecord).delete()
            db.commit()

    @staticmethod
    def site_telemetry(message_id: str | None = None) -> dict:
        return {
            "schema_version": "1.0",
            "site_id": "greenhouse_001",
            "device_id": "greenhouse_001_s3",
            "message_id": message_id or str(uuid.uuid4()),
            "sampled_at": 1_910_000_000_000,
            "sensors": {
                "temperature_c": 25.5,
                "illuminance_lux": None,
                "soil_moisture_pct": 61.0,
                "co2_ppm": 680,
            },
            "quality": {"illuminance_lux": "sensor_error"},
            "actuators": {
                "pump": {"supported": True, "desired": 70, "actual": 65, "unit": "percent"},
                "heater": {"supported": True, "desired": 0, "actual": 0, "unit": "percent"},
                "grow_light": {"supported": True, "desired": 30, "actual": 30, "unit": "percent"},
            },
        }

    def test_missing_device_and_validation(self) -> None:
        self.assertEqual(self.client.get("/api/device/latest").status_code, 404)

        invalid = telemetry("sensairshuttle_001", 1_710_000_000)
        invalid["sensors"]["humidity"] = 120
        self.assertEqual(self.client.post("/api/device/telemetry", json=invalid).status_code, 422)

    def test_weather_city_index_is_province_first_and_excludes_counties(self) -> None:
        province_matches = search_region_options("河")["items"]
        self.assertEqual([item["name"] for item in province_matches], ["河北", "河南"])
        self.assertTrue(all(item["level"] == "province" for item in province_matches))

        city_matches = search_region_options("无锡")["items"]
        self.assertEqual(len(city_matches), 1)
        self.assertEqual(city_matches[0]["name"], "无锡")
        self.assertEqual(city_matches[0]["province"], "江苏")
        self.assertEqual(city_matches[0]["level"], "city")

        county_matches = search_region_options("江阴")["items"]
        self.assertEqual(county_matches, [])

    def test_telemetry_latest_history_status_and_device_isolation(self) -> None:
        first = self.client.post(
            "/api/device/telemetry",
            json=telemetry("sensairshuttle_001", 1_710_000_000, 25.0),
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["timestamp"], 1_710_000_000_000)

        second = self.client.post(
            "/api/device/telemetry",
            json=telemetry("sensairshuttle_001", 1_710_000_010_000, 27.0),
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["timestamp"], 1_710_000_010_000)
        self.client.post("/api/device/telemetry", json=telemetry("other-device", 1_710_000_020, 31.0))

        latest = self.client.get("/api/device/latest").json()
        self.assertEqual(latest["device_id"], "sensairshuttle_001")
        self.assertEqual(latest["timestamp"], 1_710_000_010_000)
        self.assertEqual(latest["sensors"]["temperature"], 27.0)
        self.assertEqual(latest["status"]["curtain"], 1)

        history = self.client.get("/api/device/history?limit=2").json()
        self.assertEqual([item["temperature"] for item in history], [25.0, 27.0])
        self.assertNotIn("pressure", history[0])

        other = self.client.get("/api/device/latest?device_id=other-device").json()
        self.assertEqual(other["sensors"]["temperature"], 31.0)
        self.assertEqual(self.client.get("/api/device/status").json(), latest["status"])

    def test_command_queue_claim_ack_and_idempotency(self) -> None:
        self.client.post("/api/device/telemetry", json=telemetry("sensairshuttle_001", 1_710_000_000))
        command = {
            "device_id": "sensairshuttle_001",
            "command": "curtain_open",
            "value": 1,
            "reason": "提高自然光照",
        }
        queued = self.client.post("/api/device/command", json=command)
        self.assertEqual(queued.status_code, 200)
        self.assertTrue(queued.json()["success"])
        self.assertIn("待执行队列", queued.json()["message"])
        self.assertEqual(queued.json()["status"]["curtain"], 1)

        unsupported = {**command, "command": "smart_control_update"}
        self.assertEqual(self.client.post("/api/device/command", json=unsupported).status_code, 422)

        claimed = self.client.get("/api/device/commands/next").json()["command"]
        self.assertEqual(claimed["state"], "dispatched")
        self.assertEqual(claimed["command"], "curtain_open")
        command_id = claimed["command_id"]
        self.assertIsNone(self.client.get("/api/device/commands/next").json()["command"])

        ack_payload = {"success": True, "message": "执行完成"}
        ack = self.client.post(f"/api/device/commands/{command_id}/ack", json=ack_payload)
        self.assertEqual(ack.status_code, 200)
        self.assertEqual(ack.json()["state"], "succeeded")

        repeated = self.client.post(f"/api/device/commands/{command_id}/ack", json=ack_payload)
        self.assertEqual(repeated.status_code, 200)
        conflicting = self.client.post(
            f"/api/device/commands/{command_id}/ack",
            json={"success": False, "message": "冲突回执"},
        )
        self.assertEqual(conflicting.status_code, 409)

    def test_position_locator_and_confirmed_dispatch(self) -> None:
        calibration = {
            "image_width": 1280,
            "image_height": 720,
            "fx": 1000,
            "fy": 1000,
            "cx": 640,
            "cy": 360,
            "camera_height_mm": 60,
            "pitch_down_deg": 30,
            "yaw_deg": 0,
            "roll_deg": 0,
        }
        with patch("position_service.call_object_locator", return_value={"detections": [
            {"label": "苹果", "confidence": 0.9, "bbox": {"x": 45, "y": 45, "width": 10, "height": 10}},
        ]}):
            located = self.client.post(
                "/api/vision/locate",
                data={"question": "苹果距离摄像头多远", "calibration": __import__("json").dumps(calibration)},
                files={"image": ("frame.jpg", b"fake-jpeg", "image/jpeg")},
            )
        self.assertEqual(located.status_code, 200)
        result = located.json()
        self.assertEqual(result["status"], "located")
        self.assertGreater(result["selected"]["ground_range_mm"], 0)

        dispatched = self.client.post(
            "/api/vision/position/send",
            json={"result_id": result["result_id"], "device_id": "greenhouse_001_s3"},
        )
        self.assertEqual(dispatched.status_code, 200)
        with SessionLocal() as db:
            command = db.query(DeviceCommandRecord).filter_by(id=dispatched.json()["command_id"]).one()
            self.assertEqual(command.command, "target_position")
            self.assertEqual(command.device_id, "greenhouse_001_s3")
            self.assertEqual(
                set(command.payload["position"]),
                {"ground_range_mm", "bearing_deg"},
            )
            self.assertNotIn("camera_range_mm", command.payload["position"])

    def test_water_gun_static_dynamic_and_stop_protocol(self) -> None:
        with SessionLocal() as db:
            command_count = db.query(DeviceCommandRecord).count()
        preview = self.client.post(
            "/api/v1/sites/greenhouse_001/water-gun/preview",
            json={
                "ground_range_mm": 850,
                "bearing_deg": 90,
                "source": "manual",
                "spray_enabled": True,
            },
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["pump_control_percent"], 50.0)
        self.assertTrue(preview.json()["simulation_only"])
        with SessionLocal() as db:
            self.assertEqual(db.query(DeviceCommandRecord).count(), command_count)
        stopped_preview = self.client.post(
            "/api/v1/sites/greenhouse_001/water-gun/preview",
            json={"ground_range_mm": 850, "bearing_deg": 90, "source": "manual", "spray_enabled": False},
        )
        self.assertEqual(stopped_preview.json()["pump_control_percent"], 0.0)

        manual_outside = self.client.post(
            "/api/v1/sites/greenhouse_001/water-gun/static",
            json={"ground_range_mm": 1701, "bearing_deg": 0, "source": "manual"},
        )
        self.assertEqual(manual_outside.status_code, 422)

        full_scale = self.client.post(
            "/api/v1/sites/greenhouse_001/water-gun/preview",
            json={"ground_range_mm": 1700, "bearing_deg": 0, "source": "vision", "spray_enabled": True},
        )
        self.assertEqual(full_scale.status_code, 200)
        self.assertEqual(full_scale.json()["pump_control_percent"], 100.0)

        rejected_start = self.client.post(
            "/api/v1/sites/greenhouse_001/water-gun/dynamic/start",
            json={
                "ground_range_mm": 500,
                "bearing_deg": 0,
                "device_id": "unknown_water_gun_device",
                "source": "manual",
            },
        )
        self.assertEqual(rejected_start.status_code, 409)
        unchanged = self.client.get("/api/v1/sites/greenhouse_001/water-gun").json()
        self.assertEqual(unchanged["mode"], "static")
        self.assertTrue(unchanged["spray_enabled"])

        visual_outside = self.client.post(
            "/api/v1/sites/greenhouse_001/water-gun/static",
            json={
                "ground_range_mm": 1500,
                "bearing_deg": -18,
                "source": "vision",
                "target_label": "苹果",
            },
        )
        self.assertEqual(visual_outside.status_code, 200)
        self.assertEqual(visual_outside.json()["bearing_deg"], -18)

        started = self.client.post(
            "/api/v1/sites/greenhouse_001/water-gun/dynamic/start",
            json={"ground_range_mm": 600, "bearing_deg": 12, "source": "manual"},
        )
        self.assertEqual(started.status_code, 200)
        session_id = started.json()["session_id"]
        self.assertTrue(started.json()["spray_enabled"])

        updated = self.client.put(
            "/api/v1/sites/greenhouse_001/water-gun/dynamic/target",
            json={"session_id": session_id, "sequence": 2, "ground_range_mm": 700, "bearing_deg": -10},
        )
        self.assertEqual(updated.status_code, 200)
        repeated = self.client.put(
            "/api/v1/sites/greenhouse_001/water-gun/dynamic/target",
            json={"session_id": session_id, "sequence": 2, "ground_range_mm": 710, "bearing_deg": -9},
        )
        self.assertEqual(repeated.status_code, 422)

        stopped = self.client.post(
            "/api/v1/sites/greenhouse_001/water-gun/dynamic/stop",
            json={"session_id": session_id, "keep_spraying": False},
        )
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json()["mode"], "static")
        self.assertFalse(stopped.json()["spray_enabled"])
        self.assertEqual(stopped.json()["ground_range_mm"], 700)
        with SessionLocal() as db:
            latest_command = db.query(DeviceCommandRecord).order_by(DeviceCommandRecord.id.desc()).first()
            self.assertIsNotNone(latest_command)
            self.assertEqual(latest_command.payload["position"], {"ground_range_mm": 700.0, "bearing_deg": -10.0})
            self.assertEqual(latest_command.payload["water_gun"]["mode"], "static")
            self.assertFalse(latest_command.payload["water_gun"]["spray_enabled"])

    def test_water_gun_assistant_cancel_previews_and_confirm_dispatches(self) -> None:
        candidate = PositionCandidate(
            id="target-1",
            label="U盘",
            confidence=0.95,
            bbox={"x": 100, "y": 100, "width": 80, "height": 40},
            camera_range_mm=820,
            ground_range_mm=750,
            bearing_deg=-12,
            anchor={"x": 140, "y": 120},
        )

        def add_action(db, result_id: str) -> EdgeAssistantAction:
            current = now_ms()
            session_id = f"edge-{uuid.uuid4()}"
            message_id = f"message-{uuid.uuid4()}"
            action = EdgeAssistantAction(
                id=f"action-{uuid.uuid4()}",
                session_id=session_id,
                site_id="greenhouse_001",
                message_id=message_id,
                action_type="water_gun_target",
                risk="high",
                state="pending",
                payload={"result_id": result_id},
                created_at=current,
                expires_at=current + 30_000,
            )
            db.add(EdgeAssistantSession(id=session_id, site_id="greenhouse_001", channel="edge_text", created_at=current, updated_at=current))
            db.add(EdgeAssistantMessage(
                id=message_id,
                session_id=session_id,
                site_id="greenhouse_001",
                role="assistant",
                channel="edge_text",
                content="请确认是否喷水。",
                created_at=current,
                message_metadata={},
            ))
            db.add(action)
            db.commit()
            return action

        with SessionLocal() as db:
            canceled_action = add_action(db, _remember(candidate))
            canceled = decide_edge_assistant_action(db, "greenhouse_001", canceled_action.id, "cancel")
            self.assertEqual(canceled.state, "canceled")
            self.assertFalse(canceled.payload["water_gun"]["spray_enabled"])
            self.assertEqual(db.query(DeviceCommandRecord).count(), 0)

            confirmed_action = add_action(db, _remember(candidate))
            confirmed = decide_edge_assistant_action(db, "greenhouse_001", confirmed_action.id, "confirm")
            self.assertEqual(confirmed.state, "confirmed")
            self.assertTrue(confirmed.payload["water_gun"]["spray_enabled"])
            command = db.query(DeviceCommandRecord).one()
            self.assertEqual(command.payload["position"], {"ground_range_mm": 750.0, "bearing_deg": -12.0})

    def test_message_id_deduplicates_telemetry(self) -> None:
        payload = telemetry("sensairshuttle_001", 1_710_000_000)
        payload["message_id"] = "reading-001"
        payload["sequence"] = 7
        first = self.client.post("/api/device/telemetry", json=payload)
        repeated = self.client.post("/api/device/telemetry", json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(first.json(), repeated.json())
        with SessionLocal() as db:
            self.assertEqual(db.query(TelemetryRecord).count(), 1)
            self.assertEqual(db.query(TelemetryReceipt).count(), 1)

    def test_target_ranges_alarm_ack_and_recovery(self) -> None:
        ranges = {
            "temperature": {"min": 24, "max": 30},
            "humidity": {"min": 55, "max": 72},
            "light": {"min": 14000, "max": 24000},
            "co2": {"min": 520, "max": 900},
            "soil_moisture": {"min": 48, "max": 66},
            "soil_ec": {"min": 1.2, "max": 2.6},
            "gas_resistance": {"min": 12000, "max": 22000},
        }
        saved = self.client.put("/api/device/alarm-settings", json={"ranges": ranges})
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["configured"])

        for index in range(2):
            self.client.post(
                "/api/device/telemetry",
                json=telemetry("sensairshuttle_001", 1_710_000_000 + index, 32.0),
            )
        self.assertEqual(self.client.get("/api/device/alarms").json(), [])

        self.client.post(
            "/api/device/telemetry",
            json=telemetry("sensairshuttle_001", 1_710_000_002, 32.0),
        )
        alarms = self.client.get("/api/device/alarms").json()
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0]["state"], "open")
        self.assertIn("高于目标范围", alarms[0]["title"])

        acknowledged = self.client.post(f"/api/device/alarms/{alarms[0]['id']}/ack")
        self.assertEqual(acknowledged.status_code, 200)
        self.assertEqual(acknowledged.json()["state"], "acknowledged")
        self.assertEqual(self.client.post(f"/api/device/alarms/{alarms[0]['id']}/ack").status_code, 200)

        for index in range(3):
            self.client.post(
                "/api/device/telemetry",
                json=telemetry("sensairshuttle_001", 1_710_000_010 + index, 30.0),
            )
        resolved = self.client.get("/api/device/alarms").json()[0]
        self.assertEqual(resolved["state"], "resolved")
        self.assertTrue(resolved["handled"])

    def test_device_health_offline_and_recovery(self) -> None:
        self.client.post("/api/device/telemetry", json=telemetry("sensairshuttle_001", 1_710_000_000))
        health = self.client.get("/api/device/health")
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()["online"])
        with SessionLocal() as db:
            presence = db.get(DevicePresence, "sensairshuttle_001")
            check_offline_devices(db, current_time_ms=presence.last_seen_at + 121_000)
        offline = self.client.get("/api/device/health").json()
        self.assertFalse(offline["online"])
        self.assertTrue(any(item["level"] == "danger" for item in self.client.get("/api/device/alarms").json()))

        self.client.post("/api/device/telemetry", json=telemetry("sensairshuttle_001", 1_710_000_010))
        self.assertTrue(self.client.get("/api/device/health").json()["online"])

    def test_mqtt_mapping_ignores_inertial_fields(self) -> None:
        payload = telemetry("sensairshuttle_001", 1_710_000_000)
        payload["sensors"]["acc_x"] = 0.1
        mapped = canonical_telemetry(payload)
        self.assertEqual(mapped.sensors.temperature, 26.5)
        self.assertNotIn("acc_x", mapped.sensors.model_dump())

    def test_every_metric_uses_user_target_boundaries(self) -> None:
        for metric_key, target in DEFAULT_ALARM_RANGES.items():
            with self.subTest(metric=metric_key):
                self.assertIsNone(direction_for(target["min"], target["min"], target["max"]))
                self.assertIsNone(direction_for(target["max"], target["min"], target["max"]))
                self.assertEqual(direction_for(target["min"] - 0.01, target["min"], target["max"]), "low")
                self.assertEqual(direction_for(target["max"] + 0.01, target["min"], target["max"]), "high")

    def test_reference_tomato_knowledge_is_idempotent(self) -> None:
        with SessionLocal() as db:
            seed_reference_tomato_knowledge(db)
            seed_reference_tomato_knowledge(db)
            bases = db.query(KnowledgeBase).filter(KnowledgeBase.name == REFERENCE_TOMATO_BASE["name"]).all()
            self.assertEqual(len(bases), 1)
            self.assertEqual(db.query(KnowledgeItem).filter(KnowledgeItem.kb_id == bases[0].id).count(), 3)

    def test_site_state_uses_null_for_unavailable_sensors(self) -> None:
        empty = self.client.get("/api/v1/sites/greenhouse_001/state")
        self.assertEqual(empty.status_code, 200)
        self.assertIsNone(empty.json()["sensors"]["temperature_c"])
        self.assertEqual(empty.json()["quality"]["temperature_c"], "unavailable")

        payload = self.site_telemetry()
        payload["actuators"]["pump"]["master_enabled"] = False
        runtime = MqttRuntime()
        published: list[dict] = []
        with patch.object(runtime, "_publish_view_state", side_effect=lambda state: published.append(state.model_dump())):
            runtime._on_message(
                None,
                None,
                SimpleNamespace(
                    topic="smartagribrain/v1/devices/greenhouse_001_s3/telemetry",
                    payload=__import__("json").dumps(payload).encode("utf-8"),
                ),
            )

        state = self.client.get("/api/v1/sites/greenhouse_001/state").json()
        self.assertEqual(state["sensors"]["temperature_c"], 25.5)
        self.assertIsNone(state["sensors"]["illuminance_lux"])
        self.assertEqual(state["quality"]["illuminance_lux"], "sensor_error")
        self.assertEqual(state["actuators"]["pump"]["actual"], 65)
        self.assertFalse(state["actuators"]["pump"]["master_enabled"])
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["site_id"], "greenhouse_001")

    def test_site_telemetry_validates_topic_and_deduplicates_uuid(self) -> None:
        message_id = str(uuid.uuid4())
        payload = self.site_telemetry(message_id)
        normalized = normalize_site_telemetry(payload, "greenhouse_001_s3")
        self.assertEqual(normalized["message_id"], message_id)
        self.assertEqual(normalized["actuators"]["pump"]["unit"], "percent")

        invalid = {**payload, "device_id": "wrong-device"}
        with self.assertRaisesRegex(ValueError, "does not match"):
            normalize_site_telemetry(invalid, "greenhouse_001_s3")
        with self.assertRaisesRegex(ValueError, "UUID"):
            normalize_site_telemetry({**payload, "message_id": "not-a-uuid"}, "greenhouse_001_s3")

        runtime = MqttRuntime()
        message = SimpleNamespace(
            topic="smartagribrain/v1/devices/greenhouse_001_s3/telemetry",
            payload=__import__("json").dumps(payload).encode("utf-8"),
        )
        runtime._on_message(None, None, message)
        runtime._on_message(None, None, message)
        with SessionLocal() as db:
            self.assertEqual(db.query(SiteSnapshotRecord).filter_by(message_id=message_id).count(), 1)

    def test_site_history_returns_every_stored_real_reading_and_keeps_sample_cache(self) -> None:
        base = now_ms() // 60_000 * 60_000

        def sample(sampled_at: int, temperature: float) -> dict:
            payload = self.site_telemetry(str(uuid.uuid4()))
            payload["sampled_at"] = sampled_at
            payload["sensors"].update({
                "temperature_c": temperature,
                "illuminance_lux": 18_000,
                "soil_moisture_pct": 58.5,
                "co2_ppm": 680,
                # Reserved fields remain accepted and stored with the raw sample.
                "humidity_pct": 62.0,
                "gas_resistance_ohm": 15_000,
                "soil_ec_ms_cm": 1.8,
            })
            return payload

        with SessionLocal() as db:
            save_site_telemetry(db, sample(base - 3 * 60_000, 24.0), "greenhouse_001_s3")
            save_site_telemetry(db, sample(base - 3 * 60_000 + 5_000, 25.0), "greenhouse_001_s3")
            save_site_telemetry(db, sample(base - 60_000, 26.0), "greenhouse_001_s3")
            save_site_telemetry(db, sample(base - 25 * 60 * 60_000, 20.0), "greenhouse_001_s3")

            self.assertEqual(db.query(SiteHistorySample).count(), 2)
            self.assertEqual(db.query(SiteSnapshotRecord).count(), 4)
            newest_first_minute = db.query(SiteHistorySample).order_by(SiteHistorySample.sampled_at).first()
            self.assertEqual(newest_first_minute.payload["sensors"]["humidity_pct"], 62.0)

        response = self.client.get("/api/v1/sites/greenhouse_001/history?hours=6")
        self.assertEqual(response.status_code, 200)
        points = response.json()
        self.assertEqual([point["temperature"] for point in points], [24.0, 25.0, 26.0])
        self.assertEqual([point["timestamp"] for point in points], sorted(point["timestamp"] for point in points))
        self.assertEqual(points[0]["humidity"], 62.0)

    def test_site_history_accepts_partial_visible_sensor_samples(self) -> None:
        base = now_ms() // 60_000 * 60_000
        payload = self.site_telemetry(str(uuid.uuid4()))
        payload["sampled_at"] = base - 60_000
        payload["sensors"].update({
            "temperature_c": 23.5,
            "illuminance_lux": None,
            "soil_moisture_pct": None,
            "co2_ppm": None,
        })

        with SessionLocal() as db:
            save_site_telemetry(db, payload, "greenhouse_001_s3")
            self.assertEqual(db.query(SiteHistorySample).count(), 1)

        response = self.client.get("/api/v1/sites/greenhouse_001/history?hours=6")
        self.assertEqual(response.status_code, 200)
        points = response.json()
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["temperature"], 23.5)
        self.assertIsNone(points[0]["light"])
        self.assertIsNone(points[0]["co2"])
        self.assertIsNone(points[0]["soil_moisture"])

    def test_site_history_backfills_existing_snapshots_after_upgrade(self) -> None:
        base = now_ms() // 60_000 * 60_000

        def sample(sampled_at: int, temperature: float) -> dict:
            payload = self.site_telemetry(str(uuid.uuid4()))
            payload["sampled_at"] = sampled_at
            payload["sensors"].update({
                "temperature_c": temperature,
                "illuminance_lux": 17_500,
                "soil_moisture_pct": 57.0,
                "co2_ppm": 660,
            })
            return normalize_site_telemetry(payload, "greenhouse_001_s3")

        with SessionLocal() as db:
            for offset, temperature in ((-2 * 60_000, 23.5), (-60_000, 24.5)):
                payload = sample(base + offset, temperature)
                db.add(
                    SiteSnapshotRecord(
                        site_id=payload["site_id"],
                        device_id=payload["device_id"],
                        message_id=payload["message_id"],
                        sampled_at=payload["sampled_at"],
                        received_at=payload["sampled_at"] + 100,
                        payload=payload,
                    )
                )
            db.commit()
            self.assertEqual(db.query(SiteHistorySample).count(), 0)

        response = self.client.get("/api/v1/sites/greenhouse_001/history?hours=6")
        self.assertEqual(response.status_code, 200)
        points = response.json()
        self.assertEqual([point["temperature"] for point in points], [23.5, 24.5])
        self.assertEqual([point["timestamp"] for point in points], sorted(point["timestamp"] for point in points))
        with SessionLocal() as db:
            self.assertEqual(db.query(SiteHistorySample).count(), 2)

    def test_site_command_is_uuid_and_succeeds_only_after_device_ack(self) -> None:
        with SessionLocal() as db:
            queued = queue_site_command(
                db,
                "greenhouse_001",
                SiteCommandRequest(target="pump", value=72, source="web_manual", reason="test"),
            )
            uuid.UUID(queued.command_id)
            self.assertEqual(queued.state, "queued")

            claimed = claim_next_site_command(db)
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.state, "dispatched")
            wire = command_wire_payload(claimed)
            self.assertEqual(wire["command"], {"operation": "set", "target": "pump", "value": 72})

            ack = acknowledge_site_command(
                db,
                {
                    "command_id": claimed.command_id,
                    "state": "executed",
                    "actual_value": 70,
                    "acknowledged_at": 1_910_000_000_100,
                },
            )
            self.assertEqual(ack.state, "succeeded")
            self.assertEqual(ack.actual_value, 70)
            repeated = acknowledge_site_command(db, {"command_id": claimed.command_id, "state": "failed"})
            self.assertEqual(repeated.state, "succeeded")

    def test_smart_control_cannot_issue_a_pump_command_while_water_gun_owns_it(self) -> None:
        response = self.client.post(
            "/api/v1/sites/greenhouse_001/commands",
            json={"target": "pump", "value": 70, "source": "smart_control", "reason": "legacy automation"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("水枪控制", response.json()["detail"][0]["msg"])

    def test_expired_site_command_is_never_dispatched(self) -> None:
        with SessionLocal() as db:
            queued = queue_site_command(
                db,
                "greenhouse_001",
                SiteCommandRequest(target="heater", value=50, source="web_manual"),
            )
            record = db.query(SiteCommandRecord).filter_by(command_id=queued.command_id).one()
            record.expires_at = 1
            db.commit()
            self.assertEqual(expire_site_commands(db), 1)
            self.assertIsNone(claim_next_site_command(db))
            db.refresh(record)
            self.assertEqual(record.state, "expired")

    def test_edge_pump_action_requires_confirmation_and_cancel_is_safe(self) -> None:
        with SessionLocal() as db:
            reply = create_edge_assistant_reply(db, "greenhouse_001", "打开水泵", None, "edge_text")
            self.assertLessEqual(len(reply.content), 120)
            self.assertEqual(len(reply.actions), 1)
            self.assertEqual(db.query(SiteCommandRecord).count(), 0)

            confirmed = decide_edge_assistant_action(db, "greenhouse_001", reply.actions[0].id, "confirm")
            self.assertEqual(confirmed.state, "confirmed")
            command = db.query(SiteCommandRecord).one()
            self.assertEqual((command.target, command.value, command.source), ("pump", 100, "edge_voice"))

        self.setUp()
        with SessionLocal() as db:
            reply = create_edge_assistant_reply(db, "greenhouse_001", "打开水泵", None, "edge_text")
            canceled = decide_edge_assistant_action(db, "greenhouse_001", reply.actions[0].id, "cancel")
            self.assertEqual(canceled.state, "canceled")
            self.assertEqual(db.query(SiteCommandRecord).count(), 0)

    def test_v2_assistant_keeps_history_and_hidden_tool_context(self) -> None:
        captured_messages: list[list[dict]] = []
        calls = 0

        def fake_deepseek(messages: list[dict], **_kwargs: object) -> dict:
            nonlocal calls
            calls += 1
            captured_messages.append(messages)
            if calls == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "tool-state-1",
                        "type": "function",
                        "function": {"name": "read_site_state", "arguments": "{}"},
                    }],
                }
            return {
                "role": "assistant",
                "content": '{"answer":"已结合上下文回答。","actions":[],"referenceIds":[]}',
            }

        session_id = f"web-{uuid.uuid4()}"
        with patch("assistant_orchestrator.deepseek_api_key", return_value="test-key"), patch(
            "assistant_orchestrator.call_deepseek_chat_message", side_effect=fake_deepseek
        ):
            first = run_assistant_turn(AssistantTurnRequest(
                session_id=session_id,
                site_id="greenhouse_001",
                channel="web",
                message_id=f"user-{uuid.uuid4()}",
                text="温度怎么样",
            ))
            second = run_assistant_turn(AssistantTurnRequest(
                session_id=session_id,
                site_id="greenhouse_001",
                channel="web",
                message_id=f"user-{uuid.uuid4()}",
                text="那湿度呢",
            ))

        self.assertEqual(first.message.content, "已结合上下文回答。")
        self.assertEqual(second.message.content, "已结合上下文回答。")
        second_turn_messages = captured_messages[-1]
        self.assertTrue(any(item.get("content") == "温度怎么样" for item in second_turn_messages))
        self.assertTrue(any(item.get("content") == "那湿度呢" for item in second_turn_messages))
        self.assertIn("site_state", "\n".join(str(item.get("content", "")) for item in second_turn_messages))

    def test_camera_configuration_question_prefetches_saved_height(self) -> None:
        captured_messages: list[dict] = []
        captured_tool_names: list[str] = []
        model_calls = 0

        def fake_deepseek(messages: list[dict], **kwargs: object) -> dict:
            nonlocal model_calls
            model_calls += 1
            captured_messages.extend(messages)
            tools = kwargs.get("tools")
            if isinstance(tools, list):
                captured_tool_names.extend(
                    str(tool.get("function", {}).get("name"))
                    for tool in tools
                    if isinstance(tool, dict)
                )
            if model_calls == 1:
                # Even if a model hallucinates an unavailable visual tool call,
                # a configuration question must never capture or locate a frame.
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "tool-invalid-locate",
                        "type": "function",
                        "function": {"name": "locate_camera_target", "arguments": '{"query":"摄像头高度"}'},
                    }],
                }
            return {
                "role": "assistant",
                "content": '{"answer":"镜头到定位平面的高度是 110 mm。","actions":[],"referenceIds":[]}',
            }

        with SessionLocal() as db:
            save_app_state_value(db, "camera-position", {
                "image_width": 1280,
                "image_height": 720,
                "fx": 1394,
                "fy": 1394,
                "cx": 640,
                "cy": 349,
                "distortion": [0, 0, 0, 0, 0],
                "camera_height_mm": 110,
                "pitch_down_deg": 1,
                "yaw_deg": -1.1,
                "roll_deg": -0.13,
            })
            save_app_state_value(db, "backend-camera", {
                "device_index": 1,
                "width": 1280,
                "height": 720,
                "fps": 15,
            })

        self.assertTrue(_is_camera_configuration_request("现在我的相机架有多高？"))
        with patch("assistant_orchestrator.deepseek_api_key", return_value="test-key"), patch(
            "assistant_orchestrator.call_deepseek_chat_message", side_effect=fake_deepseek
        ), patch("assistant_orchestrator.camera_service.fresh_snapshot") as fresh_snapshot:
            response = run_assistant_turn(AssistantTurnRequest(
                session_id=f"web-{uuid.uuid4()}",
                site_id="greenhouse_001",
                channel="web",
                message_id=f"user-{uuid.uuid4()}",
                text="现在我的相机架有多高？",
            ))

        prompt_text = "\n".join(str(item.get("content", "")) for item in captured_messages)
        self.assertIn('"camera_height_mm": 110.0', prompt_text)
        self.assertEqual(response.message.content, "已保存的镜头安装高度为 110 mm（11 cm），指镜头到定位平面的垂直高度。")
        self.assertNotIn("locate_camera_target", captured_tool_names)
        self.assertNotIn("inspect_camera", captured_tool_names)
        fresh_snapshot.assert_not_called()

    def test_dashboard_context_reads_business_sections_and_excludes_ui_drafts(self) -> None:
        with SessionLocal() as db:
            save_app_state_value(db, "dashboard", {
                "smartControlEnabled": True,
                "smartControlLastPublishAt": 1_910_000_000_000,
                "chatInput": "不应发送的输入草稿",
                "assistantWidth": 520,
            })
            execution = _execute_tool(
                db,
                "greenhouse_001",
                "读取控制状态",
                "read_dashboard_context",
                {"sections": ["overview", "control", "water_gun"]},
                lambda _text: None,
            )

        self.assertIn("overview", execution.content)
        self.assertIn("water_gun", execution.content)
        self.assertTrue(execution.content["control"]["smartControlEnabled"])
        self.assertNotIn("chatInput", execution.content["control"])
        self.assertNotIn("assistantWidth", execution.content["control"])

    def test_camera_configuration_reports_missing_saved_values_and_offline_runtime(self) -> None:
        with SessionLocal() as db, patch("assistant_orchestrator.camera_service.status", return_value={
            "connected": False,
            "width": 0,
            "height": 0,
            "captured_at": 0,
            "error": "camera unavailable",
        }):
            execution = _execute_tool(
                db,
                "greenhouse_001",
                "读取相机配置",
                "read_camera_configuration",
                {},
                lambda _text: None,
            )

        self.assertFalse(execution.content["position_config_saved"])
        self.assertFalse(execution.content["runtime"]["connected"])
        self.assertEqual(execution.content["runtime"]["error"], "camera unavailable")

    def test_dashboard_context_handles_empty_saved_business_data(self) -> None:
        with SessionLocal() as db, patch("weather_service.weather_bundle", return_value={
            "city": "无锡",
            "current": {"available": False, "reason": "not configured"},
            "registered_capabilities": [{"key": "grid"}],
        }):
            execution = _execute_tool(
                db,
                "greenhouse_001",
                "读取页面业务信息",
                "read_dashboard_context",
                {"sections": ["history", "weather", "alarms", "disease", "knowledge"]},
                lambda _text: None,
            )

        self.assertEqual(execution.content["history"]["points"], [])
        self.assertEqual(execution.content["alarms"]["recent"], [])
        self.assertEqual(execution.content["disease"]["recent_photos"], [])
        self.assertIn("bases", execution.content["knowledge"])
        self.assertNotIn("registered_capabilities", execution.content["weather"])

    def test_sse_event_format_contains_retry_event_and_json_data(self) -> None:
        stream = site_event_bus.stream("greenhouse_001")
        self.assertEqual(next(stream), "retry: 2000\n\n")
        site_event_bus.publish("greenhouse_001", "telemetry", {"temperature_c": 26.0})
        event = next(stream)
        self.assertIn("event: telemetry", event)
        self.assertIn('data: {"temperature_c":26.0}', event)
        stream.close()

    def test_mqtt_topics_are_device_scoped(self) -> None:
        runtime = MqttRuntime()
        self.assertEqual(
            runtime._parse_topic("smartagribrain/v1/devices/greenhouse_001_s3/command_ack"),
            ("greenhouse_001_s3", "command_ack"),
        )
        with self.assertRaisesRegex(ValueError, "outside"):
            runtime._parse_topic("other/v1/devices/greenhouse_001_s3/telemetry")


if __name__ == "__main__":
    unittest.main()
