import time
import os
import logging
import asyncio
import json
import re
import uuid
from typing import Any, Callable

from dotenv import load_dotenv
import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from assistant_service import assistant_chat
from agri_text_normalizer import TextInterpretation, normalize_agri_text
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
from site_models import EdgeAssistantAction
from speech_service import (
    MAX_RECORDING_SECONDS,
    NoSpeechRecognized,
    PcmAudio,
    SpeechProviderError,
    SpeechProviderNotConfigured,
    encode_voice_response,
    get_live_transcriber,
    get_speech_provider,
    voice_spoken_text,
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

logger = logging.getLogger("smartagribrain.voice")


_PENDING_CANCEL_PHRASES = {
    "取消", "取消操作", "取消执行", "算了", "算了吧", "不要", "不要执行", "不用", "不用执行",
    "不执行", "别执行", "别执行了", "停止执行", "先不执行", "暂时不要执行", "cancel",
}
_PENDING_CONFIRM_PHRASES = {
    "确认", "确认执行", "确认操作", "确定", "确定执行", "同意", "同意执行", "可以执行",
    "开始执行", "执行", "执行吧", "好的确认", "好的执行", "没问题执行", "confirm",
}


def _pending_action_decision(text: str) -> str | None:
    """Resolve only explicit, short replies while a device action is pending."""

    compact = re.sub(r"[\s，。！？!?、；;：:\"'“”‘’]", "", str(text or "").strip().lower())
    # Check cancellation first: negative replies often also contain “执行”.
    if compact in _PENDING_CANCEL_PHRASES:
        return "cancel"
    if compact in _PENDING_CONFIRM_PHRASES:
        return "confirm"
    return None

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


def _assistant_reply_for_transcript(
    *,
    transcript: str,
    site_id: str,
    session_id: str | None,
    pending_action_id: str | None,
    turn_id: str | None = None,
    delta: Callable[[str], None] | None = None,
    event: Callable[[str, dict[str, Any]], None] | None = None,
) -> tuple[str, list[dict[str, Any]], str, TextInterpretation, str]:
    interpretation = normalize_agri_text(transcript, voice_input=True)
    normalized = interpretation.normalized.strip().rstrip("。！!？?")
    with SessionLocal() as db:
        pending_decision = _pending_action_decision(normalized) if pending_action_id else None
        if pending_action_id and pending_decision == "confirm":
            action = decide_edge_assistant_action(db, site_id, pending_action_id, pending_decision)
            answer = "已确认，正在执行操作。" if action.state == "confirmed" else "这个操作已经无法执行。"
            actions = [action.model_dump(mode="json")]
            active_session_id = session_id or ""
            next_input = "none"
        elif pending_action_id and pending_decision == "cancel":
            action = decide_edge_assistant_action(db, site_id, pending_action_id, pending_decision)
            answer = "已取消，不会执行这个操作。"
            actions = [action.model_dump(mode="json")]
            active_session_id = session_id or ""
            next_input = "none"
        elif pending_action_id:
            pending_action = db.get(EdgeAssistantAction, pending_action_id)
            if (
                pending_action is not None
                and pending_action.site_id == site_id
                and pending_action.state == "pending"
                and pending_action.expires_at >= round(time.time() * 1000)
            ):
                answer = "请说确认或取消。"
                actions = [{
                    "id": pending_action.id,
                    "type": pending_action.action_type,
                    "risk": pending_action.risk,
                    "state": pending_action.state,
                    "payload": pending_action.payload,
                    "expires_at": pending_action.expires_at,
                }]
                active_session_id = pending_action.session_id
                next_input = "confirmation"
            else:
                answer = "这个待确认操作已经失效，请重新发出请求。"
                actions = []
                active_session_id = session_id or ""
                next_input = "none"
        else:
            reply = create_edge_assistant_reply(
                db,
                site_id,
                interpretation.normalized,
                session_id,
                "edge_text",
                message_id=turn_id,
                delta=delta,
                event=event,
            )
            answer = reply.content
            actions = [action.model_dump(mode="json") for action in reply.actions]
            active_session_id = reply.session_id
            next_input = reply.next_input
    return answer, actions, active_session_id, interpretation, next_input


def _voice_reply(
    *,
    pcm: bytes,
    sample_rate_hz: int,
    site_id: str,
    session_id: str | None,
    pending_action_id: str | None,
    turn_id: str | None = None,
) -> bytes:
    total_started = time.perf_counter()
    upload_bytes = len(pcm)
    provider = get_speech_provider()
    asr_started = time.perf_counter()
    transcript = provider.transcribe(PcmAudio(pcm, sample_rate_hz))
    asr_ms = (time.perf_counter() - asr_started) * 1000
    logger.info(
        "Voice ASR completed in %.0f ms, pcm_bytes=%d, sample_rate_hz=%d",
        asr_ms,
        upload_bytes,
        sample_rate_hz,
    )
    assistant_started = time.perf_counter()
    answer, actions, active_session_id, interpretation, next_input = _assistant_reply_for_transcript(
        transcript=transcript,
        site_id=site_id,
        session_id=session_id,
        pending_action_id=pending_action_id,
        turn_id=turn_id,
    )
    assistant_ms = (time.perf_counter() - assistant_started) * 1000
    logger.info("Voice assistant reply completed in %.0f ms, actions=%d", assistant_ms, len(actions))

    spoken_answer = voice_spoken_text(answer)
    tts_started = time.perf_counter()
    audio = provider.synthesize(spoken_answer, sample_rate_hz=24_000)
    tts_ms = (time.perf_counter() - tts_started) * 1000
    total_ms = (time.perf_counter() - total_started) * 1000
    logger.info(
        "Voice TTS completed in %.0f ms, spoken_chars=%d, audio_bytes=%d",
        tts_ms,
        len(spoken_answer),
        len(audio.data),
    )
    logger.info(
        "Voice turn completed in %.0f ms (asr=%.0f ms, assistant=%.0f ms, tts=%.0f ms, upload_bytes=%d)",
        total_ms,
        asr_ms,
        assistant_ms,
        tts_ms,
        upload_bytes,
    )
    return encode_voice_response(
        {
            "schema_version": "1.0",
            "session_id": active_session_id,
            "transcript": interpretation.normalized,
            "original_transcript": interpretation.original,
            "input_interpretation": interpretation.as_dict(),
            "answer": answer,
            "actions": actions,
            "next_input": next_input,
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
    x_voice_turn_id: str | None = Header(default=None),
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
            turn_id=x_voice_turn_id,
        )
    except SpeechProviderNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except NoSpeechRecognized as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except SpeechProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except (httpx.HTTPError, OSError) as error:
        raise HTTPException(status_code=502, detail="语音服务暂时不可用") from error
    return Response(content=payload, media_type="application/vnd.smartagribrain.voice")


class _SpeechSegmenter:
    def __init__(self, limit: int = 20) -> None:
        self.buffer = ""
        self.limit = limit
        # A streamed answer is synthesized in several independent requests.
        # Splitting at an arbitrary character count can put the two characters
        # of a word (for example, "打开") in different requests and produces an
        # audible pause inside the word.  Only punctuation is a safe boundary.
        self.boundaries = "。！？!?；;，,、：:"

    def feed(self, delta: str) -> list[str]:
        self.buffer += delta
        segments: list[str] = []
        while self.buffer:
            split_at = -1
            for index, character in enumerate(self.buffer):
                if character in self.boundaries:
                    split_at = index + 1
                    break
            if split_at < 0:
                break
            segment = voice_spoken_text(self.buffer[:split_at], limit=0).strip()
            self.buffer = self.buffer[split_at:]
            if segment:
                segments.append(segment)
        return segments

    def flush(self) -> str:
        segment = voice_spoken_text(self.buffer, limit=0).strip()
        self.buffer = ""
        return segment


@app.websocket("/api/v1/assistant/voice/live")
async def assistant_voice_live(websocket: WebSocket) -> None:
    await websocket.accept()
    transcriber = None
    failure_stage = "protocol"
    background_tasks: list[asyncio.Task[Any]] = []
    try:
        start_message = await asyncio.wait_for(websocket.receive_json(), timeout=8)
        if start_message.get("type") != "start":
            await websocket.send_json({"type": "error", "code": "PROTOCOL_ERROR", "message": "缺少语音开始消息"})
            await websocket.close(code=1003)
            return
        if int(start_message.get("sample_rate_hz") or 0) != 16_000:
            await websocket.send_json({"type": "error", "code": "AUDIO_FORMAT", "message": "语音必须为 16 kHz PCM"})
            await websocket.close(code=1003)
            return
        turn_id = str(start_message.get("turn_id") or f"voice-{uuid.uuid4()}")[:64]
        site_id = str(start_message.get("site_id") or os.getenv("DEFAULT_SITE_ID", "greenhouse_001"))[:80]
        session_id = str(start_message.get("session_id") or "")[:64] or None
        pending_action_id = str(start_message.get("pending_action_id") or "")[:64] or None
        failure_stage = "asr"
        transcriber = get_live_transcriber()
        await asyncio.to_thread(transcriber.start)
        await websocket.send_json({"type": "ready", "turn_id": turn_id})

        pcm_bytes = 0
        last_partial = ""
        recording_stopped_at = 0.0
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect()
            pcm = message.get("bytes")
            if isinstance(pcm, bytes):
                pcm_bytes += len(pcm)
                if pcm_bytes > 16_000 * 2 * MAX_RECORDING_SECONDS:
                    await websocket.send_json({"type": "error", "code": "AUDIO_TOO_LONG", "message": "本次录音时间过长"})
                    await websocket.close(code=1009)
                    return
                partial = await asyncio.to_thread(transcriber.feed, pcm)
                if partial and partial != last_partial:
                    last_partial = partial
                    await websocket.send_json({"type": "partial_transcript", "text": partial})
                continue
            raw_text = message.get("text")
            if not isinstance(raw_text, str):
                continue
            control = json.loads(raw_text)
            if control.get("type") == "cancel":
                await websocket.send_json({"type": "canceled"})
                return
            if control.get("type") == "end":
                recording_stopped_at = time.perf_counter()
                break

        await websocket.send_json({"type": "assistant_status", "stage": "transcribing", "message": "正在识别你说的话"})
        transcript = await asyncio.to_thread(transcriber.finish)
        asr_finished_at = time.perf_counter()
        interpretation = normalize_agri_text(transcript, voice_input=True)
        await websocket.send_json({
            "type": "final_transcript",
            "text": interpretation.normalized,
            "original_text": interpretation.original,
            "corrected": interpretation.corrected,
            "turn_id": turn_id,
        })
        failure_stage = "deepseek"

        loop = asyncio.get_running_loop()
        outbound: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        tts_segments: asyncio.Queue[str | None] = asyncio.Queue()
        display_deltas: asyncio.Queue[tuple[str, bool] | None] = asyncio.Queue()
        send_lock = asyncio.Lock()
        segmenter = _SpeechSegmenter()
        streamed_answer = ""
        first_model_text_at = 0.0
        first_display_at = 0.0
        first_model_display_at = 0.0
        first_audio_at = 0.0
        thinking_started_at = 0.0
        thinking_finished_at = 0.0
        deepseek_thinking_ms = 0
        max_edge_answer_chars = 60
        interim_sent = False
        interim_sent_at = 0.0

        def queue_event(name: str, payload: dict[str, Any]) -> None:
            nonlocal thinking_started_at, thinking_finished_at, deepseek_thinking_ms
            if name == "thinking_started" and thinking_started_at <= 0:
                thinking_started_at = time.perf_counter()
            elif name == "thinking_finished" and thinking_finished_at <= 0:
                thinking_finished_at = time.perf_counter()
            if name == "thinking_finished" and thinking_started_at > 0 and thinking_finished_at > 0:
                reported_ms = payload.get("thinking_ms")
                if isinstance(reported_ms, (int, float)):
                    deepseek_thinking_ms = max(0, round(reported_ms))
                else:
                    deepseek_thinking_ms = round((thinking_finished_at - thinking_started_at) * 1000)
                payload = {
                    **payload,
                    "thinking_ms": deepseek_thinking_ms,
                }
            loop.call_soon_threadsafe(outbound.put_nowait, ("json", {"type": name, **payload}))

        def queue_delta(value: str, *, model_text: bool = True) -> None:
            nonlocal streamed_answer, first_model_text_at, thinking_finished_at
            if not value:
                return
            value = value.replace("*", "").replace("_", "").replace("`", "").replace("#", "")
            if not value:
                return
            if model_text and first_model_text_at <= 0:
                first_model_text_at = time.perf_counter()
                if thinking_finished_at <= 0:
                    thinking_finished_at = first_model_text_at
            remaining = max_edge_answer_chars - len(streamed_answer) if model_text else len(value)
            accepted = value[:remaining]
            if not accepted:
                return
            if model_text:
                streamed_answer += accepted
            for offset in range(0, len(accepted), 4):
                loop.call_soon_threadsafe(
                    display_deltas.put_nowait,
                    (accepted[offset: offset + 4], model_text),
                )
            for segment in segmenter.feed(accepted):
                loop.call_soon_threadsafe(tts_segments.put_nowait, segment)

        async def send_worker() -> None:
            while True:
                kind, payload = await outbound.get()
                if kind == "done":
                    return
                async with send_lock:
                    if kind == "bytes":
                        await websocket.send_bytes(payload)
                    else:
                        await websocket.send_json(payload)

        async def delta_worker() -> None:
            nonlocal first_display_at, first_model_display_at
            while True:
                delta_item = await display_deltas.get()
                if delta_item is None:
                    return
                delta_value, model_text = delta_item
                if first_display_at <= 0:
                    first_display_at = time.perf_counter()
                if model_text and first_model_display_at <= 0:
                    first_model_display_at = time.perf_counter()
                await outbound.put(("json", {"type": "assistant_delta", "text": delta_value}))
                # Keep a readable type-on effect even if the model returns one
                # large JSON delta instead of genuinely incremental tokens.
                await asyncio.sleep(0.04)

        async def tts_worker() -> None:
            nonlocal first_audio_at
            provider = get_speech_provider()
            audio_started = False
            timeout_seconds = float(getattr(provider, "timeout_seconds", 45))

            def start_segment(segment: str) -> tuple[asyncio.Queue[tuple[str, Any]], asyncio.Task[None]]:
                chunks: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

                def synthesize() -> None:
                    try:
                        # Each synthesis has its own client, so one following sentence can
                        # be prepared while the current sentence is still being streamed.
                        with httpx.Client(timeout=timeout_seconds) as client:
                            stream_method = getattr(provider, "synthesize_stream", None)
                            if callable(stream_method):
                                pcm_parts = stream_method(segment, sample_rate_hz=24_000, client=client)
                            else:
                                pcm_parts = (provider.synthesize(segment, sample_rate_hz=24_000).data,)
                            for pcm_chunk in pcm_parts:
                                if pcm_chunk:
                                    loop.call_soon_threadsafe(chunks.put_nowait, ("pcm", pcm_chunk))
                    except Exception as error:  # forwarded into the request coroutine
                        loop.call_soon_threadsafe(chunks.put_nowait, ("error", error))
                    finally:
                        loop.call_soon_threadsafe(chunks.put_nowait, ("done", None))

                return chunks, asyncio.create_task(asyncio.to_thread(synthesize))

            current: tuple[asyncio.Queue[tuple[str, Any]], asyncio.Task[None]] | None = None
            prefetched: tuple[asyncio.Queue[tuple[str, Any]], asyncio.Task[None]] | None = None
            input_closed = False
            pending_audio_get: asyncio.Task[tuple[str, Any]] | None = None
            pending_segment_get: asyncio.Task[str | None] | None = None
            # C5 consumes 24 kHz mono S16LE at 960 bytes per 20 ms.  Keep the
            # WebSocket stream at that clock instead of queuing whole TTS
            # sentences at once, which can overflow its local PCM ring.
            pcm_frame_bytes = 960
            pcm_frame_seconds = 0.020
            next_pcm_frame_at: float | None = None
            try:
                while current is not None or not input_closed:
                    if current is None:
                        if prefetched is not None:
                            current = prefetched
                            prefetched = None
                            continue
                        if pending_segment_get is not None:
                            segment = await pending_segment_get
                            pending_segment_get = None
                        else:
                            segment = await tts_segments.get()
                        if segment is None:
                            input_closed = True
                            break
                        current = start_segment(segment)
                    if prefetched is None and not input_closed and pending_segment_get is None:
                        pending_segment_get = asyncio.create_task(tts_segments.get())
                    if pending_audio_get is None:
                        pending_audio_get = asyncio.create_task(current[0].get())
                    wait_for = [pending_audio_get]
                    if pending_segment_get is not None:
                        wait_for.append(pending_segment_get)
                    ready, _ = await asyncio.wait(wait_for, return_when=asyncio.FIRST_COMPLETED)
                    if pending_segment_get is not None and pending_segment_get in ready:
                        segment = pending_segment_get.result()
                        pending_segment_get = None
                        if segment is None:
                            input_closed = True
                        else:
                            # At most the playing sentence plus one next sentence run at once.
                            prefetched = start_segment(segment)
                    if pending_audio_get in ready:
                        kind, payload = pending_audio_get.result()
                        pending_audio_get = None
                        if kind == "error":
                            raise payload
                        if kind == "done":
                            await current[1]
                            current = prefetched
                            prefetched = None
                            continue
                        pcm_chunk = payload
                        if not audio_started:
                            audio_started = True
                            first_audio_at = time.perf_counter()
                            await outbound.put(("json", {
                                "type": "timing",
                                "first_audio_after_asr_ms": round((first_audio_at - asr_finished_at) * 1000),
                                "first_audio_after_thinking_ms": round(
                                    (first_audio_at - thinking_finished_at) * 1000
                                ) if thinking_finished_at else None,
                                "non_thinking_to_first_audio_ms": max(
                                    0,
                                    round((first_audio_at - recording_stopped_at) * 1000)
                                    - deepseek_thinking_ms,
                                ),
                            }))
                            await outbound.put(("json", {
                                "type": "audio_start",
                                "encoding": "pcm_s16le",
                                "sample_rate_hz": 24_000,
                            }))
                        for offset in range(0, len(pcm_chunk), pcm_frame_bytes):
                            await outbound.put(("bytes", pcm_chunk[offset: offset + pcm_frame_bytes]))
                            if next_pcm_frame_at is None:
                                next_pcm_frame_at = time.perf_counter()
                            next_pcm_frame_at += pcm_frame_seconds
                            delay = next_pcm_frame_at - time.perf_counter()
                            if delay > 0:
                                await asyncio.sleep(delay)
                            else:
                                # Do not accumulate a stale schedule when a
                                # send is temporarily delayed by the network.
                                next_pcm_frame_at = time.perf_counter()
            finally:
                for task in (pending_audio_get, pending_segment_get):
                    if task is not None and not task.done():
                        task.cancel()
                for entry in (current, prefetched):
                    if entry is not None and not entry[1].done():
                        entry[1].cancel()
            # This is the final completion signal even when a provider returns
            # an empty stream; C5 must not wait for its long socket timeout.
            await outbound.put(("json", {"type": "audio_done"}))

        sender = asyncio.create_task(send_worker())
        deltas = asyncio.create_task(delta_worker())
        tts = asyncio.create_task(tts_worker())
        background_tasks.extend((sender, deltas, tts))
        model = asyncio.create_task(asyncio.to_thread(
            _assistant_reply_for_transcript,
            transcript=transcript,
            site_id=site_id,
            session_id=session_id,
            pending_action_id=pending_action_id,
            turn_id=turn_id,
            delta=queue_delta,
            event=queue_event,
        ))

        async def first_response_deadline() -> None:
            nonlocal interim_sent, interim_sent_at
            remaining = 7 - (time.perf_counter() - recording_stopped_at)
            if remaining > 0:
                await asyncio.sleep(remaining)
            if streamed_answer or model.done():
                return
            interim_sent = True
            interim_sent_at = time.perf_counter()
            await outbound.put(("json", {
                "type": "assistant_status",
                "stage": "continuing",
                "message": "正在继续分析",
            }))
            queue_delta("我正在继续分析，请稍候。", model_text=False)

        deadline = asyncio.create_task(first_response_deadline())
        background_tasks.append(deadline)
        answer, actions, active_session_id, model_interpretation, next_input = await model
        if not mqtt_runtime.publish_voice_control(
            answer=answer,
            actions=actions,
            session_id=active_session_id,
            user_content=transcript,
            turn_id=turn_id,
            next_input=next_input,
        ):
            logger.warning(
                "C5 voice result was persisted but immediate MQTT delivery was unavailable; "
                "the C5 will recover it after reconnect"
            )
        if not deadline.done():
            deadline.cancel()
            await asyncio.gather(deadline, return_exceptions=True)
        if not streamed_answer:
            queue_delta(answer)
        await display_deltas.put(None)
        await deltas
        tail = segmenter.flush()
        if tail:
            await tts_segments.put(tail)
        await tts_segments.put(None)
        await outbound.put(("json", {
            "type": "assistant_done",
            "answer": answer,
            "actions": actions,
            "next_input": next_input,
            "session_id": active_session_id,
            "input_interpretation": model_interpretation.as_dict(),
            "timing_ms": {
                # T1 - T0: recognition plus request preparation up to the
                # instant immediately before the DeepSeek call.
                "asr_after_stop": round(
                    ((thinking_started_at or asr_finished_at) - recording_stopped_at) * 1000
                ),
                "raw_asr_after_stop": round((asr_finished_at - recording_stopped_at) * 1000),
                "assistant_prep_after_asr": round(
                    (thinking_started_at - asr_finished_at) * 1000
                ) if thinking_started_at else None,
                "first_text_after_asr": round((first_display_at - asr_finished_at) * 1000) if first_display_at else None,
                "deepseek_thinking": round(
                    deepseek_thinking_ms
                ) if thinking_started_at and thinking_finished_at else None,
                "first_text_after_thinking": round(
                    (first_model_display_at - thinking_finished_at) * 1000
                ) if first_model_display_at and thinking_finished_at else None,
                "non_thinking_to_first_text": max(
                    0,
                    round((first_display_at - recording_stopped_at) * 1000)
                    - deepseek_thinking_ms,
                ) if first_display_at else None,
                "deadline_interim_sent": interim_sent,
                "deadline_interim_after_stop": round(
                    (interim_sent_at - recording_stopped_at) * 1000
                ) if interim_sent_at else None,
            },
        }))
        failure_stage = "tts"
        await tts
        await outbound.put(("done", None))
        await sender
        failure_stage = "done"
        await websocket.close(code=1000)
    except WebSocketDisconnect:
        logger.info("C5 live voice client disconnected")
    except SpeechProviderNotConfigured as error:
        await websocket.send_json({"type": "error", "code": "SPEECH_NOT_CONFIGURED", "message": str(error)})
    except NoSpeechRecognized as error:
        await websocket.send_json({"type": "error", "code": "NO_SPEECH", "message": str(error)})
    except SpeechProviderError as error:
        code = "TTS_ERROR" if failure_stage == "tts" else "ASR_ERROR"
        await websocket.send_json({"type": "error", "code": code, "message": str(error)})
    except json.JSONDecodeError:
        await websocket.send_json({"type": "error", "code": "PROTOCOL_ERROR", "message": "语音协议数据格式错误"})
    except (httpx.HTTPError, OSError):
        await websocket.send_json({"type": "error", "code": "NETWORK_ERROR", "message": "语音服务网络暂时不可用"})
    except Exception as error:
        logger.exception("Live voice turn failed")
        try:
            code = "DEEPSEEK_ERROR" if failure_stage == "deepseek" else "TTS_ERROR" if failure_stage == "tts" else "VOICE_ERROR"
            await websocket.send_json({"type": "error", "code": code, "message": "语音服务暂时不可用"})
        except Exception:
            pass
    finally:
        for task in background_tasks:
            if not task.done():
                task.cancel()
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
        if transcriber is not None:
            await asyncio.to_thread(transcriber.close)
