from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session

from app_state_models import AppState


DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "local_demo")


def get_app_state(db: Session, state_key: str, user_id: str = DEFAULT_USER_ID) -> AppState | None:
    return (
        db.query(AppState)
        .filter(AppState.user_id == user_id, AppState.state_key == state_key)
        .first()
    )


def read_app_state_value(db: Session, state_key: str, user_id: str = DEFAULT_USER_ID) -> Dict[str, Any]:
    state = get_app_state(db, state_key, user_id)
    if state is None or not isinstance(state.value, dict):
        return {}
    return state.value


def save_app_state_value(
    db: Session,
    state_key: str,
    value: Dict[str, Any],
    user_id: str = DEFAULT_USER_ID,
) -> AppState:
    state = get_app_state(db, state_key, user_id)
    now = datetime.utcnow()
    if state is None:
        state = AppState(user_id=user_id, state_key=state_key, value=value, created_at=now, updated_at=now)
        db.add(state)
    else:
        state.value = value
        state.updated_at = now
    db.commit()
    db.refresh(state)
    return state
