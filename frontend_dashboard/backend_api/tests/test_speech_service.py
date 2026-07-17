from __future__ import annotations

import base64
import json

import pytest

from speech_service import PcmAudio, _decode_tts_lines, decode_voice_response, encode_voice_response, speech_text


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


def test_speech_text_removes_markdown_and_code() -> None:
    assert speech_text("## 建议\n**先浇水** `20%`。") == "建议 先浇水 20%。"
