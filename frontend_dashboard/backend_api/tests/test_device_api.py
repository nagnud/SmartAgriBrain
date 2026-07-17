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
        with SessionLocal() as db:
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
