from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


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
from kb_models import KnowledgeBase, KnowledgeItem  # noqa: E402
from kb_service import REFERENCE_TOMATO_BASE, seed_reference_tomato_knowledge  # noqa: E402
from region_service import search_region_options  # noqa: E402


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
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        engine.dispose()
        TEMP_DIR.cleanup()

    def setUp(self) -> None:
        with SessionLocal() as db:
            db.query(AlarmRuleState).delete()
            db.query(AlarmRecord).delete()
            db.query(DeviceAlarmSetting).delete()
            db.query(TelemetryReceipt).delete()
            db.query(DevicePresence).delete()
            db.query(DeviceCommandRecord).delete()
            db.query(TelemetryRecord).delete()
            db.commit()

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


if __name__ == "__main__":
    unittest.main()
