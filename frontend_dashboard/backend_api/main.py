import time
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from assistant_service import assistant_chat
from app_state_routes import router as app_state_router
from database import init_database
from farm_advice_service import analyze_farm_advice
from kb_routes import router as kb_router
from photo_routes import router as photo_router
from photo_service import UPLOAD_ROOT, ensure_upload_root
from schemas import (
    AssistantChatRequest,
    AssistantChatResponse,
    FarmAdviceRequest,
    FarmAdviceResponse,
    HealthResponse,
)

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
app.include_router(photo_router)
app.mount("/uploads", StaticFiles(directory=UPLOAD_ROOT, check_dir=False), name="uploads")


@app.on_event("startup")
def startup() -> None:
    ensure_upload_root()
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


@app.post("/api/vision/disease")
async def post_vision_disease(image: UploadFile = File(...)) -> dict[str, Any]:
    await image.read()
    return {
        "image_url": "",
        "crop": "tomato",
        "model": "YOLO11n-demo",
        "detections": [
            {
                "id": "det-1",
                "label": "疑似叶斑病",
                "class_name": "leaf_spot",
                "confidence": 0.88,
                "bbox": {"x": 31, "y": 24, "width": 30, "height": 28},
                "severity": "medium",
            },
            {
                "id": "det-2",
                "label": "早期霜霉风险",
                "class_name": "downy_mildew",
                "confidence": 0.74,
                "bbox": {"x": 58, "y": 48, "width": 22, "height": 20},
                "severity": "low",
            },
        ],
        "summary": "检测到 2 处疑似病斑，整体为中等风险，建议结合湿度趋势复核。",
        "explanation": "图像中存在不规则黄褐色斑块，叠加近期湿度偏高，符合番茄叶斑病或霜霉病早期风险特征。",
        "suggestions": [
            "立即检查叶背是否有霉层，并拍摄更清晰的近景图片复核。",
            "优先通风降湿，避免叶面长时间结露。",
            "隔离明显病叶，必要时请人工确认后再用药。",
        ],
        "processed_at": int(time.time() * 1000),
    }


@app.post("/api/v1/assistant/chat", response_model=AssistantChatResponse)
def post_assistant_chat(payload: AssistantChatRequest) -> AssistantChatResponse:
    return assistant_chat(payload)
