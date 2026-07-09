from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool
    service: str


class KnowledgeReference(BaseModel):
    itemId: int
    chunkId: int
    title: str
    content: str
    score: float = 0


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
    knowledge_base_id: Optional[int] = None
    current_view: Optional[str] = None
    knowledge_bases: List[Dict[str, Any]] = Field(default_factory=list)
    knowledge_items: List[Dict[str, Any]] = Field(default_factory=list)
    command_results: List[Dict[str, Any]] = Field(default_factory=list)


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


class VoiceTranscriptionResponse(BaseModel):
    ok: bool = True
    text: str = ""
    partial: bool = True
    final: bool = False
    message: str = ""


class VoiceTranscriptionStatus(BaseModel):
    ok: bool = True
    configured: bool = False
    provider: str = "backend"
    model: str = ""
    message: str = ""
