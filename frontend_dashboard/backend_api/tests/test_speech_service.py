from __future__ import annotations

import base64
import json

import pytest

from agri_text_normalizer import normalize_agri_text
from assistant_orchestrator import (
    _AnswerDeltaDecoder,
    _fast_edge_device_action,
    _format_water_gun_duration,
    _is_water_gun_spray_request,
    _parse_water_gun_duration_seconds,
    _short_edge_answer,
)
from main import _SpeechSegmenter, _pending_action_decision
from speech_service import (
    DoubaoSpeechProvider,
    PcmAudio,
    _decode_tts_line,
    _decode_tts_lines,
    decode_voice_response,
    encode_voice_response,
    speech_text,
    voice_spoken_text,
)


def test_default_tts_profile_uses_granted_female_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOLC_SPEECH_APP_ID", "test-app")
    monkeypatch.setenv("VOLC_SPEECH_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("VOLC_TTS_RESOURCE_ID", raising=False)
    monkeypatch.delenv("VOLC_TTS_VOICE_TYPE", raising=False)

    provider = DoubaoSpeechProvider()
    headers, body = provider._tts_request("你好，我是智慧农场助手。", 24_000)

    assert provider.tts_resource_id == "seed-tts-2.0"
    assert provider.tts_voice_type == "zh_female_vv_uranus_bigtts"
    assert headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert body["req_params"]["speaker"] == "zh_female_vv_uranus_bigtts"


@pytest.mark.parametrize("text", ["确认", "确认执行。", "可以执行", "好的，执行", "执行吧", "confirm"])
def test_pending_action_accepts_explicit_voice_confirmation(text: str) -> None:
    assert _pending_action_decision(text) == "confirm"


@pytest.mark.parametrize("text", ["取消", "算了吧", "不要执行", "不执行", "别执行了", "cancel"])
def test_pending_action_accepts_explicit_voice_cancellation(text: str) -> None:
    assert _pending_action_decision(text) == "cancel"


@pytest.mark.parametrize("text", ["今天天气怎么样", "执行前先解释一下", "不确定", "好的"])
def test_pending_action_rejects_ambiguous_voice_reply(text: str) -> None:
    assert _pending_action_decision(text) is None


def test_fast_edge_heater_request_creates_confirmation_action() -> None:
    reply = _fast_edge_device_action("打开加热器")
    assert reply is not None
    assert reply.actions[0].payload["command"] == "heater_on"
    assert "直接说确认或取消" in reply.answer


def test_voice_envelope_keeps_metadata_separate_from_pcm() -> None:
    pcm = PcmAudio(data=b"\x01\x00\x02\x00", sample_rate_hz=24_000)
    payload = encode_voice_response(
        {"transcript": "打开水泵", "answer": "是否执行？", "actions": [{"state": "pending"}]},
        pcm,
    )

    metadata, decoded_pcm = decode_voice_response(payload)

    assert metadata["transcript"] == "打开水泵"
    assert metadata["actions"][0]["state"] == "pending"
    assert decoded_pcm == pcm.data


def test_voice_envelope_rejects_unknown_magic() -> None:
    with pytest.raises(ValueError, match="invalid voice response"):
        decode_voice_response(b"NOPE\x00\x00\x00\x00")


def test_tts_ndjson_audio_chunks_are_joined() -> None:
    body = b"\n".join(
        [
            json.dumps({"code": 0, "data": base64.b64encode(b"ab").decode()}).encode(),
            json.dumps({"code": 0, "data": base64.b64encode(b"cd").decode()}).encode(),
            json.dumps({"code": 20000000}).encode(),
        ]
    )

    assert _decode_tts_lines(body) == b"abcd"


def test_tts_ndjson_audio_line_can_be_forwarded_immediately() -> None:
    line = json.dumps({"code": 0, "data": base64.b64encode(b"first").decode()})

    assert _decode_tts_line(line) == b"first"


def test_speech_text_removes_markdown_and_code() -> None:
    assert speech_text("## 建议\n**先浇水** `20%`。") == "建议 先浇水 20%。"


def test_voice_spoken_text_prefers_sentence_boundary() -> None:
    first = "A" * 50 + "。"
    second = "B" * 200 + "。"

    assert voice_spoken_text(first + second, limit=120) == first


def test_voice_spoken_text_caps_long_sentence() -> None:
    spoken = voice_spoken_text("A" * 220, limit=80)

    assert spoken == "A" * 80 + "。"


@pytest.mark.parametrize(
    ("raw", "expected", "corrected"),
    [
        ("教一下水", "浇一下水", True),
        ("交一下水", "浇一下水", True),
        ("教我浇水", "教我浇水", False),
        ("交水费", "交水费", False),
    ],
)
def test_agriculture_homophone_normalizer_is_conservative(
    raw: str,
    expected: str,
    corrected: bool,
) -> None:
    interpretation = normalize_agri_text(raw)

    assert interpretation.normalized == expected
    assert interpretation.corrected is corrected
    assert interpretation.original == raw


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("对橡皮胶水", "对橡皮浇水"),
        ("胶水", "浇水"),
        ("开始罐盖", "开始灌溉"),
        ("给番茄是非", "给番茄施肥"),
        ("土壤适度太低", "土壤湿度太低"),
        ("请喷谁", "请喷水"),
    ],
)
def test_voice_normalizer_uses_agriculture_context_for_asr_homophones(raw: str, expected: str) -> None:
    interpretation = normalize_agri_text(raw, voice_input=True)

    assert interpretation.normalized == expected
    assert interpretation.corrected is True
    assert interpretation.replacements


@pytest.mark.parametrize("raw", ["胶水怎么用", "这个胶棒粘不牢", "人生的是非", "交水费"])
def test_voice_normalizer_preserves_clear_non_agriculture_meanings(raw: str) -> None:
    interpretation = normalize_agri_text(raw, voice_input=True)

    assert interpretation.normalized == raw
    assert interpretation.corrected is False


def test_object_directed_watering_uses_water_gun_instead_of_pump_fast_path() -> None:
    normalized = normalize_agri_text("对橡皮胶水", voice_input=True).normalized

    assert normalized == "对橡皮浇水"
    assert _is_water_gun_spray_request(normalized) is True
    assert _fast_edge_device_action(normalized) is None


def test_explicit_pump_watering_still_uses_pump_fast_path() -> None:
    reply = _fast_edge_device_action("打开水泵浇水")

    assert reply is not None
    assert reply.actions[0].payload["command"] == "pump_on"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("喷一分五十三秒", 113),
        ("喷1分钟53秒", 113),
        ("持续 00:01:53", 113),
        ("喷 1m53s", 113),
        ("喷九十秒", 90),
        ("喷二十三小时五十九分五十九秒", 86_399),
        ("喷零秒", None),
        ("喷24小时", None),
        ("持续 00:60:00", None),
    ],
)
def test_water_gun_duration_parser_supports_common_expressions(text: str, expected: int | None) -> None:
    assert _parse_water_gun_duration_seconds(text) == expected


def test_water_gun_duration_confirmation_text_is_spoken_naturally() -> None:
    assert _format_water_gun_duration(3_713) == "1 小时 1 分钟 53 秒"


def test_answer_delta_decoder_only_releases_answer_text() -> None:
    deltas: list[str] = []
    decoder = _AnswerDeltaDecoder(deltas.append)

    decoder.feed('{"answer":"请浇')
    decoder.feed('水。","actions":[{"tool":"set_actuator"}]}')
    decoder.finish("请浇水。")

    assert "".join(deltas) == "请浇水。"
    assert "actions" not in "".join(deltas)


def test_streaming_tts_segmenter_only_emits_at_natural_boundaries() -> None:
    segmenter = _SpeechSegmenter(limit=8)

    assert segmenter.feed("先浇一次水。再") == ["先浇一次水。"]
    assert segmenter.feed("观察土壤湿度变化") == []
    assert segmenter.flush() == "再观察土壤湿度变化"


def test_streaming_tts_segmenter_does_not_split_a_word_at_chunk_boundary() -> None:
    segmenter = _SpeechSegmenter(limit=4)

    assert segmenter.feed("请先打") == []
    assert segmenter.feed("开风机，") == ["请先打开风机，"]
    assert segmenter.flush() == ""


def test_edge_answer_is_hard_limited_to_two_short_sentences() -> None:
    answer = "温度是 25℃。湿度是 60%。这里还有一段设备端不需要主动播报的建议。"

    assert _short_edge_answer(answer) == "温度是 25℃。湿度是 60%。"
    assert len(_short_edge_answer("很长" * 50)) <= 61
