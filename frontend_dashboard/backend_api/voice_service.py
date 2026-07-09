from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List

import httpx

from schemas import VoiceTranscriptionResponse


@dataclass
class VoiceSession:
    mime_type: str
    chunks: List[bytes] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)


VOICE_SESSIONS: Dict[str, VoiceSession] = {}
SESSION_TTL_SECONDS = 180
MAX_SESSION_BYTES = 16 * 1024 * 1024


def speech_api_key() -> str:
    return (
        os.getenv("SPEECH_TRANSCRIBE_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )


def speech_model() -> str:
    return os.getenv("SPEECH_TRANSCRIBE_MODEL", "whisper-1").strip() or "whisper-1"


def speech_transcribe_url() -> str:
    explicit_url = os.getenv("SPEECH_TRANSCRIBE_URL", "").strip()
    if explicit_url:
        return explicit_url
    base_url = os.getenv("SPEECH_TRANSCRIBE_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
    return f"{base_url}/audio/transcriptions"


def cleanup_voice_sessions() -> None:
    now = time.time()
    expired = [
        session_id
        for session_id, session in VOICE_SESSIONS.items()
        if now - session.updated_at > SESSION_TTL_SECONDS
    ]
    for session_id in expired:
        VOICE_SESSIONS.pop(session_id, None)


def normalize_language(language: str) -> str:
    value = language.strip().lower()
    if value.startswith("zh"):
        return "zh"
    return value or "zh"


def filename_for_mime(mime_type: str) -> str:
    if "ogg" in mime_type:
        return "voice.ogg"
    if "mp4" in mime_type or "m4a" in mime_type:
        return "voice.m4a"
    if "wav" in mime_type:
        return "voice.wav"
    return "voice.webm"


def call_speech_transcription(audio_bytes: bytes, mime_type: str, language: str) -> str:
    api_key = speech_api_key()
    if not api_key:
        raise RuntimeError("SPEECH_TRANSCRIBE_API_KEY is not configured")

    timeout = float(os.getenv("SPEECH_TRANSCRIBE_TIMEOUT_SECONDS", "45"))
    headers = {"Authorization": f"Bearer {api_key}"}
    data = {
        "model": speech_model(),
        "language": normalize_language(language),
        "response_format": "json",
    }
    files = {
        "file": (
            filename_for_mime(mime_type),
            audio_bytes,
            mime_type or "application/octet-stream",
        )
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(speech_transcribe_url(), headers=headers, data=data, files=files)
        response.raise_for_status()
        payload = response.json()

    text = payload.get("text", "")
    if not isinstance(text, str):
        raise RuntimeError("speech transcription response missing text")
    return text.strip()


def transcribe_voice_chunk(
    *,
    session_id: str,
    sequence: int,
    is_final: bool,
    language: str,
    mime_type: str,
    audio_bytes: bytes,
) -> VoiceTranscriptionResponse:
    cleanup_voice_sessions()
    session = VOICE_SESSIONS.get(session_id)
    if session is None or sequence == 0:
        session = VoiceSession(mime_type=mime_type)
        VOICE_SESSIONS[session_id] = session

    session.mime_type = mime_type or session.mime_type
    session.chunks.append(audio_bytes)
    session.updated_at = time.time()
    combined_audio = b"".join(session.chunks)

    if len(combined_audio) > MAX_SESSION_BYTES:
        VOICE_SESSIONS.pop(session_id, None)
        return VoiceTranscriptionResponse(
            ok=False,
            text="",
            partial=not is_final,
            final=is_final,
            message="录音太长，请缩短单次语音输入。",
        )

    if not speech_api_key():
        if is_final:
            VOICE_SESSIONS.pop(session_id, None)
        return VoiceTranscriptionResponse(
            ok=False,
            text="",
            partial=not is_final,
            final=is_final,
            message="后端还没有配置语音识别 API Key，请设置 SPEECH_TRANSCRIBE_API_KEY 或 OPENAI_API_KEY。",
        )

    try:
        text = call_speech_transcription(combined_audio, session.mime_type, language)
    except Exception as error:
        print(f"voice transcription failed: {error}")
        if is_final:
            VOICE_SESSIONS.pop(session_id, None)
        return VoiceTranscriptionResponse(
            ok=False,
            text="",
            partial=not is_final,
            final=is_final,
            message=f"后端语音识别失败：{error}",
        )

    if is_final:
        VOICE_SESSIONS.pop(session_id, None)
    return VoiceTranscriptionResponse(
        ok=True,
        text=text,
        partial=not is_final,
        final=is_final,
        message="语音已识别" if text else "暂未识别到文字",
    )
