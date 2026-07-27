from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from site_events import site_event_bus
from site_schemas import (
    EdgeAssistantActionResponse,
    EdgeAssistantConversationResponse,
    EdgeAssistantDecisionRequest,
    EdgeAssistantMessageRequest,
    EdgeAssistantMessageResponse,
    SiteCommandRequest,
    SiteCommandResponse,
    SiteHistoryPoint,
    SiteState,
)
from site_service import (
    create_edge_assistant_reply,
    decide_edge_assistant_action,
    get_edge_conversation,
    get_site_history,
    get_site_state,
    queue_site_command,
)


router = APIRouter(prefix="/api/v1/sites", tags=["sites"])


@router.get("/{site_id}/state", response_model=SiteState)
def read_site_state(site_id: str, db: Session = Depends(get_db)) -> SiteState:
    return get_site_state(db, site_id)


@router.get("/{site_id}/history", response_model=list[SiteHistoryPoint])
def read_site_history(
    site_id: str,
    hours: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
) -> list[SiteHistoryPoint]:
    return get_site_history(db, site_id, hours)


@router.get("/{site_id}/events")
def stream_site_events(site_id: str) -> StreamingResponse:
    return StreamingResponse(
        site_event_bus.stream(site_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{site_id}/commands", response_model=SiteCommandResponse, status_code=202)
def create_site_command(
    site_id: str,
    payload: SiteCommandRequest,
    db: Session = Depends(get_db),
) -> SiteCommandResponse:
    return queue_site_command(db, site_id, payload)


@router.post("/{site_id}/assistant/messages", response_model=EdgeAssistantMessageResponse)
def create_assistant_message(
    site_id: str,
    payload: EdgeAssistantMessageRequest,
    db: Session = Depends(get_db),
) -> EdgeAssistantMessageResponse:
    try:
        return create_edge_assistant_reply(db, site_id, payload.text, payload.session_id, payload.channel)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{site_id}/assistant/conversation", response_model=EdgeAssistantConversationResponse)
def read_assistant_conversation(
    site_id: str,
    session_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> EdgeAssistantConversationResponse:
    return get_edge_conversation(db, site_id, session_id)


@router.post(
    "/{site_id}/assistant/actions/{action_id}/decision",
    response_model=EdgeAssistantActionResponse,
)
def decide_assistant_action(
    site_id: str,
    action_id: str,
    payload: EdgeAssistantDecisionRequest,
    db: Session = Depends(get_db),
) -> EdgeAssistantActionResponse:
    try:
        return decide_edge_assistant_action(db, site_id, action_id, payload.decision)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
