import time
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from assistant_service import assistant_chat
from agri_source_routes import router as agri_source_router
from app_state_routes import router as app_state_router
from database import init_database
from device_routes import router as device_router
from farm_advice_service import analyze_farm_advice
from kb_routes import router as kb_router
from photo_routes import router as photo_router
from photo_service import UPLOAD_ROOT, ensure_upload_root
from monitoring_runtime import device_monitor_runtime
from mqtt_service import mqtt_runtime
from schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    FarmAdviceRequest,
    FarmAdviceResponse,
    HealthResponse,
)
from vision_service import analyze_disease_image
from weather_service import current_payload, search_cities, weather_bundle

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
app.mount("/uploads", StaticFiles(directory=UPLOAD_ROOT, check_dir=False), name="uploads")


@app.on_event("startup")
def startup() -> None:
    ensure_upload_root()
    init_database()
    device_monitor_runtime.start()
    mqtt_runtime.start()


@app.on_event("shutdown")
def shutdown() -> None:
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
