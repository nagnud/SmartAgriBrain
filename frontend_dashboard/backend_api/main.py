from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from assistant_service import assistant_chat
from app_state_routes import router as app_state_router
from database import init_database
from farm_advice_service import analyze_farm_advice
from kb_routes import router as kb_router
from schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    FarmAdviceRequest,
    FarmAdviceResponse,
    HealthResponse,
    VoiceTranscriptionResponse,
    VoiceTranscriptionStatus,
)
from voice_service import speech_configured, speech_model, transcribe_voice_chunk

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

app.include_router(kb_router)
app.include_router(app_state_router)


@app.on_event("startup")
def startup() -> None:
    init_database()


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, service="smartagribrain-local-api")


@app.post("/api/ai/analyze", response_model=FarmAdviceResponse)
def post_ai_analyze(payload: FarmAdviceRequest) -> FarmAdviceResponse:
    return analyze_farm_advice(payload)


@app.post("/api/v1/farm/ai/analyze", response_model=FarmAdviceResponse)
def post_v1_farm_ai_analyze(payload: FarmAdviceRequest) -> FarmAdviceResponse:
    return analyze_farm_advice(payload)


@app.post("/api/v1/assistant/chat", response_model=AssistantChatResponse)
def post_assistant_chat(payload: AssistantChatRequest) -> AssistantChatResponse:
    return assistant_chat(payload)


@app.get("/api/v1/assistant/voice/status", response_model=VoiceTranscriptionStatus)
def get_assistant_voice_status() -> VoiceTranscriptionStatus:
    configured = speech_configured()
    return VoiceTranscriptionStatus(
        ok=True,
        configured=configured,
        provider="backend",
        model=speech_model(),
        message="后端语音识别 API Key 已配置。" if configured else "后端未配置语音识别 API Key，前端将直接使用浏览器语音识别。",
    )


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
