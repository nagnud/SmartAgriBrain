import time
import os
from typing import Any

from dotenv import load_dotenv
import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from assistant_service import assistant_chat
from assistant_v2_routes import router as assistant_v2_router
from agri_source_routes import router as agri_source_router
from app_state_routes import router as app_state_router
from database import SessionLocal, init_database
from device_routes import router as device_router
from device_service import queue_command
from farm_advice_service import analyze_farm_advice
from kb_routes import router as kb_router
from photo_routes import router as photo_router
from photo_service import UPLOAD_ROOT, ensure_upload_root
from monitoring_runtime import device_monitor_runtime
from mqtt_service import mqtt_runtime
from site_service import create_edge_assistant_reply, decide_edge_assistant_action
from speech_service import (
    MAX_RECORDING_SECONDS,
    PcmAudio,
    SpeechProviderError,
    SpeechProviderNotConfigured,
    encode_voice_response,
    get_speech_provider,
)
from schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    CameraPositionConfig,
    FarmAdviceRequest,
    FarmAdviceResponse,
    HealthResponse,
    PositionDispatchRequest,
    PositionDispatchResponse,
)
from site_routes import router as site_router
from camera_routes import configured_camera, router as camera_router
from camera_service import camera_service
from vision_service import analyze_disease_image
from position_service import locate_object, take_position_result
from position_capture_service import (
    cleanup_expired_position_captures,
    ensure_position_capture_root,
    position_capture_cleanup_runtime,
    read_position_capture,
)
from database import get_db
from device_schemas import DeviceCommandRequest
from sqlalchemy.orm import Session
from weather_service import current_payload, search_cities, weather_bundle
from water_gun_routes import router as water_gun_router
from water_gun_service import water_gun_runtime

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
app.include_router(agri_source_router)
app.include_router(app_state_router)
app.include_router(photo_router)
app.include_router(device_router)
app.include_router(site_router)
app.include_router(assistant_v2_router)
app.include_router(camera_router)
app.include_router(water_gun_router)
app.mount("/uploads", StaticFiles(directory=UPLOAD_ROOT, check_dir=False), name="uploads")


@app.on_event("startup")
def startup() -> None:
    ensure_upload_root()
    ensure_position_capture_root()
    cleanup_expired_position_captures()
    init_database()
    with SessionLocal() as db:
        camera = configured_camera(db)
    camera_service.configure(camera.device_index, camera.width, camera.height, camera.fps)
    camera_service.start()
    position_capture_cleanup_runtime.start()
    device_monitor_runtime.start()
    mqtt_runtime.start()
    water_gun_runtime.start()


@app.on_event("shutdown")
def shutdown() -> None:
    water_gun_runtime.stop()
    camera_service.stop()
    position_capture_cleanup_runtime.stop()
    mqtt_runtime.stop()
    device_monitor_runtime.stop()


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True, service="smartagribrain-local-api")


@app.post("/api/ai/analyze", response_model=FarmAdviceResponse)
def post_ai_analyze(payload: FarmAdviceRequest) -> FarmAdviceResponse:
    return analyze_farm_advice(payload)


@app.post("/api/v1/farm/ai/analyze", response_model=FarmAdviceResponse)
def post_v1_farm_ai_analyze(payload: FarmAdviceRequest) -> FarmAdviceResponse:
    return analyze_farm_advice(payload)


@app.post("/api/vision/disease")
async def post_vision_disease(
    image: UploadFile = File(...),
    retrieval_mode: str = Form("auto", pattern="^(auto|force|off)$"),
) -> dict[str, Any]:
    return await analyze_disease_image(image, retrieval_mode)  # type: ignore[arg-type]


@app.post("/api/vision/locate")
async def post_vision_locate(
    image: UploadFile = File(...),
    question: str = Form(..., min_length=1, max_length=800),
    calibration: str = Form(...),
) -> dict[str, Any]:
    try:
        config = CameraPositionConfig.model_validate_json(calibration)
    except Exception as error:
        raise HTTPException(status_code=422, detail="相机定位参数格式无效。") from error
    content_type = (image.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=400, detail="仅支持 jpg、png 或 webp 图像。")
    result = locate_object(await image.read(), content_type, question, config)
    return result.model_dump(mode="json")


@app.post("/api/vision/position/send", response_model=PositionDispatchResponse)
def post_position_send(payload: PositionDispatchRequest, db: Session = Depends(get_db)) -> PositionDispatchResponse:
    stored_result = take_position_result(payload.result_id)
    if stored_result is None:
        raise HTTPException(status_code=404, detail="定位结果已过期，请重新识别后再发送。")
    candidate, _captured_at = stored_result
    position = {
        "ground_range_mm": candidate.ground_range_mm,
        "bearing_deg": candidate.bearing_deg,
    }
    try:
        queued = queue_command(
            db,
            DeviceCommandRequest(
                device_id=payload.device_id,
                command="target_position",
                value=1,
                reason="发送目标地面极坐标",
                position=position,
            ),
        )
    except Exception as error:
        raise HTTPException(status_code=409, detail=f"位置消息未进入设备队列：{error}") from error
    command_id = int(queued.command.get("id", 0) or 0)
    if command_id <= 0:
        raise HTTPException(status_code=500, detail="位置消息队列创建失败。")
    return PositionDispatchResponse(success=True, command_id=command_id, message="目标极坐标已进入待发送队列。")


@app.get("/api/v1/position-captures/{capture_id}.jpg")
def get_position_capture(capture_id: str) -> Response:
    image = read_position_capture(capture_id)
    if image is None:
        raise HTTPException(status_code=404, detail="定位截图不存在或已超过 24 小时，请重新查询目标位置。")
    return Response(
        content=image,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


@app.get("/api/weather/current")
def get_weather_current(city: str | None = None) -> dict[str, Any]:
    return current_payload(city)


@app.get("/api/weather/bundle")
def get_weather_bundle(city: str | None = None) -> dict[str, Any]:
    return weather_bundle(city)


@app.get("/api/weather/cities")
def get_weather_cities(q: str) -> dict[str, Any]:
    return search_cities(q)


@app.post("/api/v1/assistant/chat", response_model=AssistantChatResponse)
def post_assistant_chat(payload: AssistantChatRequest) -> AssistantChatResponse:
    return assistant_chat(payload)


def _voice_reply(
    *,
    pcm: bytes,
    sample_rate_hz: int,
    site_id: str,
    session_id: str | None,
    pending_action_id: str | None,
) -> bytes:
    provider = get_speech_provider()
    transcript = provider.transcribe(PcmAudio(pcm, sample_rate_hz))
    normalized = transcript.strip().rstrip("。！!？?")

    with SessionLocal() as db:
        if pending_action_id and normalized in {"确认", "确认执行", "确定", "执行"}:
            action = decide_edge_assistant_action(db, site_id, pending_action_id, "confirm")
            answer = "已确认，正在执行操作。" if action.state == "confirmed" else "这个操作已经无法执行。"
            actions = [action.model_dump(mode="json")]
            active_session_id = session_id or ""
        elif pending_action_id and normalized in {"取消", "取消操作", "不要执行", "不执行"}:
            action = decide_edge_assistant_action(db, site_id, pending_action_id, "cancel")
            answer = "已取消，不会执行这个操作。"
            actions = [action.model_dump(mode="json")]
            active_session_id = session_id or ""
        else:
            reply = create_edge_assistant_reply(db, site_id, transcript, session_id, "edge_text")
            answer = reply.content
            actions = [action.model_dump(mode="json") for action in reply.actions]
            active_session_id = reply.session_id

    audio = provider.synthesize(answer, sample_rate_hz=24_000)
    return encode_voice_response(
        {
            "schema_version": "1.0",
            "session_id": active_session_id,
            "transcript": transcript,
            "answer": answer,
            "actions": actions,
            "audio": {
                "encoding": "pcm_s16le",
                "sample_rate_hz": audio.sample_rate_hz,
                "bits_per_sample": audio.bits_per_sample,
                "channels": audio.channels,
                "byte_length": len(audio.data),
            },
        },
        audio,
    )


@app.get("/api/v1/assistant/voice/status")
def get_voice_status() -> dict[str, Any]:
    provider = get_speech_provider()
    configured = bool(getattr(provider, "app_id", "") and getattr(provider, "access_token", ""))
    return {
        "configured": configured,
        "asr_sample_rate_hz": 16_000,
        "tts_sample_rate_hz": 24_000,
        "max_recording_seconds": MAX_RECORDING_SECONDS,
    }


@app.post("/api/v1/assistant/voice")
async def post_assistant_voice(
    request: Request,
    site_id: str | None = None,
    x_audio_sample_rate: int = Header(default=16_000),
    x_assistant_session_id: str | None = Header(default=None),
    x_pending_action_id: str | None = Header(default=None),
) -> Response:
    if x_audio_sample_rate != 16_000:
        raise HTTPException(status_code=415, detail="audio must be 16 kHz PCM")
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "audio/pcm":
        raise HTTPException(status_code=415, detail="content-type must be audio/pcm")
    pcm = await request.body()
    if len(pcm) < x_audio_sample_rate // 2:
        raise HTTPException(status_code=422, detail="recording is too short")
    if len(pcm) > x_audio_sample_rate * 2 * MAX_RECORDING_SECONDS:
        raise HTTPException(status_code=413, detail="recording is too long")
    if len(pcm) % 2:
        raise HTTPException(status_code=422, detail="PCM byte length must be even")

    resolved_site_id = (site_id or os.getenv("DEFAULT_SITE_ID", "greenhouse_001")).strip()
    try:
        payload = await run_in_threadpool(
            _voice_reply,
            pcm=pcm,
            sample_rate_hz=x_audio_sample_rate,
            site_id=resolved_site_id,
            session_id=x_assistant_session_id,
            pending_action_id=x_pending_action_id,
        )
    except SpeechProviderNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except SpeechProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (httpx.HTTPError, OSError) as error:
        raise HTTPException(status_code=502, detail="语音服务暂时不可用") from error
    return Response(content=payload, media_type="application/vnd.smartagribrain.voice")
