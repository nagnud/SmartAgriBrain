from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from assistant_orchestrator import (
    assistant_turn_runtime,
    forget_preference,
    list_preferences,
    save_preference,
)
from database import get_db
from schemas import AssistantPreferenceList, AssistantTurnAccepted, AssistantTurnRequest
from site_schemas import EdgeAssistantActionResponse, EdgeAssistantDecisionRequest
from site_service import decide_edge_assistant_action


router = APIRouter(prefix="/api/v1/assistant", tags=["assistant-v2"])


class PreferenceSaveRequest(BaseModel):
    site_id: str = Field(default="greenhouse_001", min_length=1, max_length=80)
    key: str = Field(..., min_length=1, max_length=80)
    value: str = Field(..., min_length=1, max_length=500)


@router.post("/turns", response_model=AssistantTurnAccepted, status_code=202)
def create_turn(payload: AssistantTurnRequest) -> AssistantTurnAccepted:
    turn_id, session_id = assistant_turn_runtime.submit(payload)
    return AssistantTurnAccepted(turn_id=turn_id, session_id=session_id)


@router.get("/turns/{turn_id}/events")
def stream_turn_events(turn_id: str) -> StreamingResponse:
    return StreamingResponse(
        assistant_turn_runtime.stream(turn_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/preferences", response_model=AssistantPreferenceList)
def read_preferences(
    site_id: str = Query(default="greenhouse_001", min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> AssistantPreferenceList:
    return list_preferences(db, site_id)


@router.post("/preferences", response_model=AssistantPreferenceList)
def write_preference(payload: PreferenceSaveRequest, db: Session = Depends(get_db)) -> AssistantPreferenceList:
    return save_preference(db, payload.site_id, payload.key, payload.value)


@router.delete("/preferences/{key}", response_model=AssistantPreferenceList)
def delete_preference(
    key: str,
    site_id: str = Query(default="greenhouse_001", min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> AssistantPreferenceList:
    return forget_preference(db, site_id, key)


@router.post("/actions/{action_id}/decision", response_model=EdgeAssistantActionResponse)
def decide_action(
    action_id: str,
    payload: EdgeAssistantDecisionRequest,
    site_id: str = Query(default="greenhouse_001", min_length=1, max_length=80),
    db: Session = Depends(get_db),
) -> EdgeAssistantActionResponse:
    try:
        return decide_edge_assistant_action(db, site_id, action_id, payload.decision)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

