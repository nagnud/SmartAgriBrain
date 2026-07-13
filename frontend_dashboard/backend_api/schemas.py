from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool
    service: str


class AiCommand(BaseModel):
    command: str
    value: int


class AiRiskFactor(BaseModel):
    key: str
    label: str
    detail: str
    state: Literal["good", "watch", "danger", "neutral"] = "watch"


class FarmAdviceRequest(BaseModel):
    device_id: str = Field(..., min_length=1)
    crop: str = "tomato"
    sensors: Dict[str, Any] = Field(default_factory=dict)
    status: Dict[str, Any] = Field(default_factory=dict)
    weather: Optional[Dict[str, Any]] = None
    weather_bundle: Optional[Dict[str, Any]] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)
    disease: Optional[Dict[str, Any]] = None
    camera_analysis: Optional[Dict[str, Any]] = None
    retrieval_mode: Literal["auto", "force", "off"] = "auto"


class FarmAdviceResponse(BaseModel):
    device_id: str
    crop: str
    ai_connected: bool = True
    risk_level: Literal["low", "medium", "high"]
    risk_score: int = Field(default=0, ge=0, le=100)
    risk_status: str = "较稳定"
    risk_factors: List[AiRiskFactor] = Field(default_factory=list)
    summary: str
    suggestions: List[str] = Field(default_factory=list)
    commands: List[AiCommand] = Field(default_factory=list)
    basis: List[str] = Field(default_factory=list)
    references: List["KnowledgeReference"] = Field(default_factory=list)
    retrievalStatus: Literal["not_used", "success", "partial", "unavailable"] = "not_used"
    updated_at: int


class KnowledgeReference(BaseModel):
    itemId: int = 0
    chunkId: int = 0
    title: str
    content: str
    score: float = 0
    referenceId: str = ""
    sourceType: Literal["local", "online"] = "local"
    sourceName: str = "本地知识库"
    url: Optional[str] = None
    publishedAt: Optional[str] = None
    retrievedAt: Optional[str] = None


AssistantActionType = Literal[
    "navigate_view",
    "open_panel",
    "device_command",
    "smart_control",
    "knowledge_base",
    "knowledge_item",
    "run_knowledge_analysis",
    "refresh_data",
]
AssistantActionRisk = Literal["normal", "medium", "high"]


class AssistantAction(BaseModel):
    id: str
    type: AssistantActionType
    title: str
    description: str = ""
    risk: AssistantActionRisk = "normal"
    payload: Dict[str, Any] = Field(default_factory=dict)


class AssistantChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    image_url: Optional[str] = None
    latest: Dict[str, Any] = Field(default_factory=dict)
    disease: Optional[Dict[str, Any]] = None
    weather: Optional[Dict[str, Any]] = None
    weather_bundle: Optional[Dict[str, Any]] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    camera_analysis: Optional[Dict[str, Any]] = None
    knowledge_base_id: Optional[int] = None
    current_view: Optional[str] = None
    knowledge_bases: List[Dict[str, Any]] = Field(default_factory=list)
    knowledge_items: List[Dict[str, Any]] = Field(default_factory=list)
    command_results: List[Dict[str, Any]] = Field(default_factory=list)
    retrieval_mode: Literal["auto", "force", "off"] = "auto"


class AssistantChatMessage(BaseModel):
    id: str
    role: Literal["assistant"] = "assistant"
    content: str
    created_at: int
    references: List[KnowledgeReference] = Field(default_factory=list)
    suggested_actions: List[AssistantAction] = Field(default_factory=list)


class AssistantChatResponse(BaseModel):
    message: AssistantChatMessage
    references: List[KnowledgeReference] = Field(default_factory=list)
    actions: List[AssistantAction] = Field(default_factory=list)
    retrievalStatus: Literal["not_used", "success", "partial", "unavailable"] = "not_used"


class AgriSourceInfo(BaseModel):
    sourceId: Literal["agrovoc", "eppo", "natesc"]
    name: str
    description: str
    sourceType: Literal["api", "website"]
    enabled: bool
    configured: bool
    status: Literal["unknown", "available", "unavailable", "needs_configuration", "disabled"]
    lastCheckedAt: Optional[str] = None
    lastError: str = ""


class AgriSourceListResponse(BaseModel):
    items: List[AgriSourceInfo] = Field(default_factory=list)


class AgriSourceUpdateRequest(BaseModel):
    enabled: bool


class AgriSourceTestResponse(BaseModel):
    source: AgriSourceInfo
    sampleCount: int = 0


class DiseasePhotoInfo(BaseModel):
    photoId: int
    url: str
    originalName: str = ""
    mimeType: str = ""
    size: int = 0
    createdAt: str
    analysisResult: Optional[Dict[str, Any]] = None


class DiseasePhotoListResponse(BaseModel):
    items: List[DiseasePhotoInfo] = Field(default_factory=list)


class DiseasePhotoAnalysisRequest(BaseModel):
    analysisResult: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseInfo(BaseModel):
    kbId: int
    name: str
    description: str = ""
    enabled: bool = True
    updatedAt: str


class KnowledgeItemInfo(BaseModel):
    itemId: int
    kbId: int
    title: str
    content: str
    updatedAt: str


class KnowledgeBaseListResponse(BaseModel):
    items: List[KnowledgeBaseInfo] = Field(default_factory=list)


class KnowledgeItemListResponse(BaseModel):
    items: List[KnowledgeItemInfo] = Field(default_factory=list)


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""


class KnowledgeBaseUpdateRequest(BaseModel):
    kbId: int = Field(..., ge=1)
    name: str = Field(..., min_length=1)
    description: str = ""


class KnowledgeBaseDeleteRequest(BaseModel):
    kbId: int = Field(..., ge=1)


class KnowledgeTextAddRequest(BaseModel):
    kbId: int = Field(..., ge=1)
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class KnowledgeItemUpdateRequest(BaseModel):
    kbId: int = Field(..., ge=1)
    itemId: int = Field(..., ge=1)
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class KnowledgeItemDeleteRequest(BaseModel):
    kbId: int = Field(..., ge=1)
    itemId: int = Field(..., ge=1)


class KnowledgeTextAddResult(BaseModel):
    itemId: int
    chunkCount: int
    updatedAt: str


class KnowledgeAnalyzeRequest(BaseModel):
    kbId: int = Field(..., ge=1)
    fieldId: str = ""
    question: str = Field(..., min_length=1)


class KnowledgeAnalyzeResult(BaseModel):
    answer: str
    references: List[KnowledgeReference] = Field(default_factory=list)
    updatedAt: str


class AppStateReadResponse(BaseModel):
    key: str
    value: Dict[str, Any] = Field(default_factory=dict)


class AppStateSaveRequest(BaseModel):
    value: Dict[str, Any] = Field(default_factory=dict)


class AppStateSaveResponse(BaseModel):
    key: str
    value: Dict[str, Any] = Field(default_factory=dict)
    updatedAt: str


class OperationSuccess(BaseModel):
    success: bool = True
