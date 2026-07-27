from __future__ import annotations

import json
from types import SimpleNamespace

from mqtt_service import MqttRuntime, mqtt_endpoint


def test_mqtt_endpoint_uses_the_emqx_uri_and_ignores_legacy_host(monkeypatch) -> None:
    # The API must not silently fall back to an old workstation Mosquitto
    # address when the explicit EMQX URI has not been configured.
    monkeypatch.delenv("MQTT_URI", raising=False)
    monkeypatch.setenv("MQTT_HOST", "192.168.3.14")
    monkeypatch.setenv("MQTT_PORT", "1883")
    assert mqtt_endpoint() is None

    monkeypatch.setenv("MQTT_URI", "mqtts://emqx.example.test")
    assert mqtt_endpoint() == ("emqx.example.test", 8883, True)


def test_mqtt_endpoint_rejects_paths_and_credentials(monkeypatch) -> None:
    # Endpoint credentials belong in the ignored environment variables, never
    # in MQTT_URI where they could leak through diagnostics or process lists.
    monkeypatch.setenv("MQTT_URI", "mqtts://user:password@emqx.example.test/topic")
    try:
        mqtt_endpoint()
    except ValueError as error:
        assert "scheme, host and optional port" in str(error)
    else:
        raise AssertionError("invalid EMQX URI was accepted")


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


def test_assistant_clear_tells_c5_that_no_action_is_pending() -> None:
    published: list[str] = []

    class FakeClient:
        def publish(self, topic: str, payload: str, *, qos: int, retain: bool) -> SimpleNamespace:
            published.append(payload)
            return SimpleNamespace(rc=0)

    runtime = MqttRuntime()
    runtime._client = FakeClient()
    runtime._mqtt = SimpleNamespace(MQTT_ERR_SUCCESS=0)

    runtime._publish_assistant_clear(session_id="session-after-confirm", recovered=True)

    payload = json.loads(published[0])
    assert payload["kind"] == "voice_control"
    assert payload["recovered"] is True
    assert payload["session_id"] == "session-after-confirm"
    assert payload["assistant"]["actions"] == []
    assert payload["assistant"]["next_input"] == "none"


def test_voice_control_accepts_protocol_v2_parameter_follow_up() -> None:
    published: list[str] = []

    class FakeClient:
        def publish(self, topic: str, payload: str, *, qos: int, retain: bool) -> SimpleNamespace:
            published.append(payload)
            return SimpleNamespace(rc=0)

    runtime = MqttRuntime()
    runtime._client = FakeClient()
    runtime._mqtt = SimpleNamespace(MQTT_ERR_SUCCESS=0)

    assert runtime.publish_voice_control(
        answer="补光灯要调到百分之几，还是切换为自动模式？",
        actions=[],
        session_id="parameter-session",
        next_input="parameter",
    )
    assert json.loads(published[0])["assistant"]["next_input"] == "parameter"
