from __future__ import annotations

import base64
import gzip
import json
import os
import re
import struct
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import websocket


VOICE_RESPONSE_MAGIC = b"SAV1"
MAX_RECORDING_SECONDS = 12
DEFAULT_ASR_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
DEFAULT_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


@dataclass(frozen=True)
class PcmAudio:
    data: bytes
    sample_rate_hz: int
    bits_per_sample: int = 16
    channels: int = 1


class SpeechToTextProvider(Protocol):
    def transcribe(self, audio: PcmAudio, *, language: str = "zh-CN") -> str: ...


class TextToSpeechProvider(Protocol):
    def synthesize(self, text: str, *, sample_rate_hz: int = 24_000) -> PcmAudio: ...


class SpeechProvider(SpeechToTextProvider, TextToSpeechProvider, Protocol):
    pass


class SpeechProviderNotConfigured(RuntimeError):
    pass


class SpeechProviderError(RuntimeError):
    pass


def _secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    lowered = value.lower()
    if not value or lowered.startswith("your-") or lowered.startswith("your_"):
        return ""
    return value


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except ValueError:
        return default


def _request_headers(app_id: str, access_token: str, resource_id: str, request_id: str) -> dict[str, str]:
    # ASR uses X-Api-App-Key. Older-console TTS applications are accepted by
    # the same AppID/AccessToken pair; both documented App header spellings are
    # sent so one backend build works with either speech endpoint generation.
    return {
        "X-Api-App-Key": app_id,
        "X-Api-App-Id": app_id,
        "X-Api-Access-Key": access_token,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": request_id,
        "X-Api-Connect-Id": request_id,
    }


def _asr_packet(payload: bytes, *, message_type: int, flags: int = 0, serialized: bool = False) -> bytes:
    compressed = gzip.compress(payload)
    serialization = 1 if serialized else 0
    header = bytes((0x11, (message_type << 4) | flags, (serialization << 4) | 1, 0x00))
    return header + struct.pack(">I", len(compressed)) + compressed


def _decode_asr_response(packet: bytes) -> dict[str, Any]:
    if len(packet) < 8:
        raise SpeechProviderError("豆包 ASR 返回了不完整的数据")
    header_size = (packet[0] & 0x0F) * 4
    message_type = packet[1] >> 4
    flags = packet[1] & 0x0F
    compression = packet[2] & 0x0F
    cursor = header_size
    if flags & 0x01:
        cursor += 4  # sequence number
    if message_type == 0xF:
        if len(packet) < cursor + 8:
            raise SpeechProviderError("豆包 ASR 返回了未知错误")
        code = struct.unpack_from(">I", packet, cursor)[0]
        cursor += 4
        size = struct.unpack_from(">I", packet, cursor)[0]
        cursor += 4
        detail = packet[cursor : cursor + size].decode("utf-8", errors="replace")
        raise SpeechProviderError(f"豆包 ASR 错误 {code}: {detail}")
    if len(packet) < cursor + 4:
        return {}
    size = struct.unpack_from(">I", packet, cursor)[0]
    cursor += 4
    payload = packet[cursor : cursor + size]
    if compression == 1 and payload:
        payload = gzip.decompress(payload)
    if not payload:
        return {}
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SpeechProviderError("豆包 ASR 返回内容无法解析") from error
    return decoded if isinstance(decoded, dict) else {}


def _find_transcript(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("text", "utterance_text"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
        for key in ("result", "results", "payload_msg", "payload"):
            text = _find_transcript(value.get(key))
            if text:
                return text
    elif isinstance(value, list):
        for item in reversed(value):
            text = _find_transcript(item)
            if text:
                return text
    return ""


def _decode_tts_lines(content: bytes) -> bytes:
    audio = bytearray()
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SpeechProviderError("豆包 TTS 返回内容无法解析") from error
        if not isinstance(item, dict):
            continue
        code = int(item.get("code", 0))
        if code not in {0, 20000000}:
            raise SpeechProviderError(f"豆包 TTS 错误 {code}: {item.get('message', '未知错误')}")
        data = item.get("data")
        if isinstance(data, str) and data:
            try:
                audio.extend(base64.b64decode(data, validate=True))
            except ValueError as error:
                raise SpeechProviderError("豆包 TTS 音频编码无效") from error
    return bytes(audio)


class DoubaoSpeechProvider:
    def __init__(self) -> None:
        self.app_id = _secret("VOLC_SPEECH_APP_ID")
        self.access_token = _secret("VOLC_SPEECH_ACCESS_TOKEN")
        self.asr_resource_id = os.getenv("VOLC_ASR_RESOURCE_ID", "volc.seedasr.sauc.duration").strip()
        self.asr_url = os.getenv("VOLC_ASR_WEBSOCKET_URL", DEFAULT_ASR_URL).strip() or DEFAULT_ASR_URL
        self.asr_sample_rate_hz = _int_env("VOLC_ASR_SAMPLE_RATE_HZ", 16_000)
        self.tts_resource_id = os.getenv("VOLC_TTS_RESOURCE_ID", "seed-tts-2.0").strip()
        self.tts_url = os.getenv("VOLC_TTS_HTTP_URL", DEFAULT_TTS_URL).strip() or DEFAULT_TTS_URL
        self.tts_voice_type = os.getenv("VOLC_TTS_VOICE_TYPE", "zh_female_vv_uranus_bigtts").strip()
        self.tts_sample_rate_hz = _int_env("VOLC_TTS_SAMPLE_RATE_HZ", 24_000)
        self.timeout_seconds = max(_int_env("VOLC_SPEECH_TIMEOUT_SECONDS", 45), 5)

    def _require_configured(self) -> None:
        if not self.app_id or not self.access_token:
            raise SpeechProviderNotConfigured("豆包语音 APP ID 或 Access Token 尚未配置")

    def transcribe(self, audio: PcmAudio, *, language: str = "zh-CN") -> str:
        self._require_configured()
        if audio.sample_rate_hz != self.asr_sample_rate_hz or audio.bits_per_sample != 16 or audio.channels != 1:
            raise ValueError("ASR 输入必须是 16 kHz、16-bit、单声道 PCM")
        if not audio.data:
            raise ValueError("ASR 输入音频为空")

        request_id = str(uuid.uuid4())
        headers = _request_headers(self.app_id, self.access_token, self.asr_resource_id, request_id)
        request = {
            "user": {"uid": request_id},
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": audio.sample_rate_hz,
                "bits": audio.bits_per_sample,
                "channel": audio.channels,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "show_utterances": True,
                "language": language,
            },
        }
        socket = websocket.create_connection(
            self.asr_url,
            header=[f"{key}: {value}" for key, value in headers.items()],
            timeout=self.timeout_seconds,
            enable_multithread=False,
        )
        transcript = ""
        try:
            socket.send_binary(
                _asr_packet(
                    json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                    message_type=0x1,
                    serialized=True,
                )
            )
            initial = socket.recv()
            if isinstance(initial, str):
                initial = initial.encode("utf-8")
            transcript = _find_transcript(_decode_asr_response(initial)) or transcript

            chunk_bytes = audio.sample_rate_hz * 2 // 5  # 200 ms
            chunks = [audio.data[offset : offset + chunk_bytes] for offset in range(0, len(audio.data), chunk_bytes)]
            for index, chunk in enumerate(chunks):
                is_last = index == len(chunks) - 1
                socket.send_binary(_asr_packet(chunk, message_type=0x2, flags=0x2 if is_last else 0))
                # The 2.0 async endpoint emits results only when recognition
                # changes. Do not wait for a response after every audio packet.
                time.sleep(0.03)

            while True:
                response = socket.recv()
                if isinstance(response, str):
                    response = response.encode("utf-8")
                flags = response[1] & 0x0F if len(response) > 1 else 0
                text = _find_transcript(_decode_asr_response(response))
                if text:
                    transcript = text
                if flags & 0x02:
                    break
        finally:
            socket.close()
        if not transcript:
            raise SpeechProviderError("没有识别到清晰语音")
        return transcript

    def synthesize(self, text: str, *, sample_rate_hz: int = 24_000) -> PcmAudio:
        self._require_configured()
        clean_text = speech_text(text)
        if not clean_text:
            raise ValueError("TTS 文本为空")
        request_id = str(uuid.uuid4())
        headers = _request_headers(self.app_id, self.access_token, self.tts_resource_id, request_id)
        headers["Content-Type"] = "application/json"
        body = {
            "user": {"uid": request_id},
            "req_params": {
                "text": clean_text[:900],
                "speaker": self.tts_voice_type,
                "audio_params": {
                    "format": "pcm",
                    "sample_rate": sample_rate_hz,
                    "speech_rate": 0,
                    "loudness_rate": 0,
                },
                "additions": json.dumps({"disable_markdown_filter": True}, ensure_ascii=False),
            },
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.tts_url, headers=headers, json=body)
            response.raise_for_status()
        pcm = _decode_tts_lines(response.content)
        if not pcm:
            raise SpeechProviderError("豆包 TTS 没有返回音频")
        return PcmAudio(data=pcm, sample_rate_hz=sample_rate_hz)


def speech_text(text: str) -> str:
    value = re.sub(r"```.*?```", "", text, flags=re.S)
    value = re.sub(r"[`#*_>\[\](){}]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def get_speech_provider() -> SpeechProvider:
    return DoubaoSpeechProvider()


def encode_voice_response(metadata: dict[str, Any], audio: PcmAudio) -> bytes:
    header = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return VOICE_RESPONSE_MAGIC + struct.pack(">I", len(header)) + header + audio.data


def decode_voice_response(payload: bytes) -> tuple[dict[str, Any], bytes]:
    if len(payload) < 8 or payload[:4] != VOICE_RESPONSE_MAGIC:
        raise ValueError("invalid voice response envelope")
    header_size = struct.unpack_from(">I", payload, 4)[0]
    if header_size > 64_000 or len(payload) < 8 + header_size:
        raise ValueError("invalid voice response header size")
    metadata = json.loads(payload[8 : 8 + header_size].decode("utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("voice response metadata must be an object")
    return metadata, payload[8 + header_size :]
