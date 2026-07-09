import time

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from schemas import (
    AssistantChatMessage,
    AssistantChatRequest,
    AssistantChatResponse,
    HealthResponse,
    KnowledgeReference,
    VoiceTranscriptionResponse,
)
from voice_service import transcribe_voice_chunk

load_dotenv()

app = FastAPI(
    title="SmartAgriBrain Local API",
    version="1.0.0",
    description="Local FastAPI backend for the SmartAgriBrain frontend assistant.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, service="smartagribrain-local-api")


@app.post("/api/v1/assistant/chat", response_model=AssistantChatResponse)
def post_assistant_chat(payload: AssistantChatRequest) -> AssistantChatResponse:
    references = [
        KnowledgeReference(
            itemId=1,
            chunkId=1,
            title="本地农业助手",
            content="当前为本地后端占位回复。接入大模型后，可在此处调用真实 LLM API，并在执行控制动作前返回待确认操作。",
            score=0.86,
        )
    ]
    latest = payload.latest or {}
    sensors = latest.get("sensors", {}) if isinstance(latest, dict) else {}
    sensor_text = ""
    if isinstance(sensors, dict) and sensors:
        sensor_text = (
            f"\n\n当前环境参考：温度 {sensors.get('temperature', '--')}，"
            f"湿度 {sensors.get('humidity', '--')}，"
            f"光照 {sensors.get('light', '--')}，"
            f"CO2 {sensors.get('co2', '--')}。"
        )

    content = (
        "我已经收到你的问题。当前后端已接通，可以处理文字、图片和语音识别后的文本。"
        "后续接入大模型 API 后，我会根据自然语言生成操作建议；涉及设备控制或目标值修改时，会先让用户确认。"
        f"{sensor_text}\n\n你的问题：{payload.question}"
    )
    message = AssistantChatMessage(
        id=f"assistant-{int(time.time() * 1000)}",
        content=content,
        created_at=int(time.time() * 1000),
        references=references,
        suggested_actions=[],
    )
    return AssistantChatResponse(message=message, references=references, actions=[])


@app.post("/api/v1/assistant/voice/transcribe", response_model=VoiceTranscriptionResponse)
async def post_assistant_voice_transcribe(
    audio: UploadFile = File(...),
    session_id: str = Form(...),
    sequence: int = Form(..., ge=0),
    is_final: bool = Form(False),
    language: str = Form("zh-CN"),
    mime_type: str = Form("audio/webm"),
) -> VoiceTranscriptionResponse:
    audio_bytes = await audio.read()
    if len(audio_bytes) == 0:
        return VoiceTranscriptionResponse(
            ok=False,
            text="",
            partial=not is_final,
            final=is_final,
            message="没有收到录音数据。",
        )

    return transcribe_voice_chunk(
        session_id=session_id,
        sequence=sequence,
        is_final=is_final,
        language=language,
        mime_type=mime_type or audio.content_type or "audio/webm",
        audio_bytes=audio_bytes,
    )
