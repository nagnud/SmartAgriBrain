from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session

from app_state_models import AppState
from schemas import CameraPositionConfig


DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "local_demo")
CAMERA_POSITION_STATE_KEY = "camera-position"


DEFAULT_CAMERA_POSITION_CONFIG: Dict[str, Any] = {
    "image_width": 1280,
    "image_height": 720,
    "fx": 1315.5,
    "fy": 1478.1,
    "cx": 605.7,
    "cy": 332.9,
    "distortion": [0, 0, 0, 0, 0],
    "camera_height_mm": 150,
    "pitch_down_deg": 15,
    "yaw_deg": -2.02,
    "roll_deg": 0.74,
}

LEGACY_CAMERA_POSITION_CONFIGS: tuple[Dict[str, Any], ...] = (
    {
        "image_width": 1280,
        "image_height": 720,
        "fx": 0,
        "fy": 0,
        "cx": 640,
        "cy": 360,
        "distortion": [],
        "camera_height_mm": 60,
        "pitch_down_deg": 30,
        "yaw_deg": 0,
        "roll_deg": 0,
    },
    {
        "image_width": 1280,
        "image_height": 720,
        "fx": 1394,
        "fy": 1394,
        "cx": 640,
        "cy": 349,
        "distortion": [0, 0, 0, 0, 0],
        "camera_height_mm": 150,
        "pitch_down_deg": 15,
        "yaw_deg": -1.1,
        "roll_deg": -0.13,
    },
    {
        "image_width": 1280,
        "image_height": 720,
        "fx": 1347.1,
        "fy": 1427.9,
        "cx": 640,
        "cy": 349,
        "distortion": [0, 0, 0, 0, 0],
        "camera_height_mm": 150,
        "pitch_down_deg": 15,
        "yaw_deg": 1.39,
        "roll_deg": 0.63,
    },
    {
        "image_width": 1280,
        "image_height": 720,
        "fx": 1347.1,
        "fy": 1427.9,
        "cx": 640,
        "cy": 349,
        "distortion": [0, 0, 0, 0, 0],
        "camera_height_mm": 150,
        "pitch_down_deg": 20,
        "yaw_deg": 1.39,
        "roll_deg": 0.63,
    },
    {
        "image_width": 1280,
        "image_height": 720,
        "fx": 1315.5,
        "fy": 1472.8,
        "cx": 605.7,
        "cy": 391.8,
        "distortion": [0, 0, 0, 0, 0],
        "camera_height_mm": 150,
        "pitch_down_deg": 20,
        "yaw_deg": -2.02,
        "roll_deg": 0.74,
    },
)


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


def default_camera_position_config() -> Dict[str, Any]:
    return CameraPositionConfig(**DEFAULT_CAMERA_POSITION_CONFIG).model_dump(mode="json")


def _float_matches(left: Any, right: Any, tolerance: float = 1e-6) -> bool:
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def _distortion_matches(left: Any, right: Any) -> bool:
    if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right):
        return False
    return all(_float_matches(left_item, right_item) for left_item, right_item in zip(left, right))


def _camera_position_matches(value: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    for key, expected_value in expected.items():
        if key == "distortion":
            if not _distortion_matches(value.get(key), expected_value):
                return False
        elif isinstance(expected_value, (float, int)):
            if not _float_matches(value.get(key), expected_value):
                return False
        elif value.get(key) != expected_value:
            return False
    return True


def camera_position_needs_default_seed(value: Dict[str, Any]) -> bool:
    if not value:
        return True
    if any(key not in value for key in DEFAULT_CAMERA_POSITION_CONFIG):
        return True
    try:
        config = CameraPositionConfig.model_validate(value)
    except ValueError:
        return True
    if not config.calibrated:
        return True
    return any(_camera_position_matches(value, legacy) for legacy in LEGACY_CAMERA_POSITION_CONFIGS)


def seed_default_camera_position(db: Session, user_id: str = DEFAULT_USER_ID) -> AppState | None:
    current = read_app_state_value(db, CAMERA_POSITION_STATE_KEY, user_id)
    if not camera_position_needs_default_seed(current):
        return None
    return save_app_state_value(db, CAMERA_POSITION_STATE_KEY, default_camera_position_config(), user_id)
