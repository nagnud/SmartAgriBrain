from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app_state_service import read_app_state_value, save_app_state_value
from database import get_db
from schemas import AppStateReadResponse, AppStateSaveRequest, AppStateSaveResponse


router = APIRouter(prefix="/api/v1/state", tags=["app-state"])


@router.get("/{state_key}", response_model=AppStateReadResponse)
def get_state(state_key: str, db: Session = Depends(get_db)) -> AppStateReadResponse:
    return AppStateReadResponse(key=state_key, value=read_app_state_value(db, state_key))


@router.post("/{state_key}", response_model=AppStateSaveResponse)
def post_state(state_key: str, payload: AppStateSaveRequest, db: Session = Depends(get_db)) -> AppStateSaveResponse:
    state = save_app_state_value(db, state_key, payload.value)
    updated_at = state.updated_at.strftime("%Y-%m-%d %H:%M")
    return AppStateSaveResponse(key=state_key, value=state.value, updatedAt=updated_at)
