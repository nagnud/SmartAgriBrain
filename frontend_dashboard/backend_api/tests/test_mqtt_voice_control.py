from __future__ import annotations

import json
from types import SimpleNamespace

from mqtt_service import MqttRuntime


def test_pending_actions_excludes_finished_and_expired_entries() -> None:
    actions = [
        {"id": "pending", "state": "pending", "expires_at": 10_001},
        {"id": "expired", "state": "pending", "expires_at": 9_999},
        {"id": "confirmed", "state": "confirmed", "expires_at": 20_000},
    ]

    assert [action["id"] for action in MqttRuntime._pending_actions(actions, current_ms=10_000)] == ["pending"]


def test_voice_control_uses_qos_transport_and_contains_pending_action() -> None:
    published: list[tuple[str, str, int, bool]] = []

    class FakeClient:
        def publish(self, topic: str, payload: str, *, qos: int, retain: bool) -> SimpleNamespace:
            published.append((topic, payload, qos, retain))
            return SimpleNamespace(rc=0)

    runtime = MqttRuntime()
    runtime._client = FakeClient()
    runtime._mqtt = SimpleNamespace(MQTT_ERR_SUCCESS=0)

    assert runtime.publish_voice_control(
        answer="请确认喷水 5 秒。",
        actions=[{"id": "action-1", "state": "pending", "expires_at": 9_999_999_999_999}],
        session_id="session-1",
        turn_id="turn-1",
    )
    topic, encoded, qos, retain = published[0]
    payload = json.loads(encoded)
    assert topic.endswith("/assistant/response")
    assert qos == 1
    assert retain is False
    assert payload["kind"] == "voice_control"
    assert payload["session_id"] == "session-1"
    assert payload["assistant"]["actions"][0]["id"] == "action-1"
    assert payload["assistant"]["next_input"] == "confirmation"


def test_voice_control_also_delivers_follow_up_question_without_action() -> None:
    published: list[str] = []

    class FakeClient:
        def publish(self, topic: str, payload: str, *, qos: int, retain: bool) -> SimpleNamespace:
            published.append(payload)
            return SimpleNamespace(rc=0)

    runtime = MqttRuntime()
    runtime._client = FakeClient()
    runtime._mqtt = SimpleNamespace(MQTT_ERR_SUCCESS=0)

    assert runtime.publish_voice_control(
        answer="已找到橡皮，需要喷多久？",
        actions=[],
        session_id="duration-session",
        next_input="duration",
    )
    payload = json.loads(published[0])
    assert payload["assistant"]["content"] == "已找到橡皮，需要喷多久？"
    assert payload["assistant"]["actions"] == []
    assert payload["assistant"]["next_input"] == "duration"


def test_voice_control_rejects_unknown_next_input_value() -> None:
    published: list[str] = []

    class FakeClient:
        def publish(self, topic: str, payload: str, *, qos: int, retain: bool) -> SimpleNamespace:
            published.append(payload)
            return SimpleNamespace(rc=0)

    runtime = MqttRuntime()
    runtime._client = FakeClient()
    runtime._mqtt = SimpleNamespace(MQTT_ERR_SUCCESS=0)

    assert runtime.publish_voice_control(
        answer="普通回答。",
        actions=[],
        session_id="ordinary-session",
        next_input="unexpected",
    )
    assert json.loads(published[0])["assistant"]["next_input"] == "none"
