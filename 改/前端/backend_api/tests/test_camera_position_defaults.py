from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

TEMP_DB = Path(tempfile.gettempdir()) / f"camera-position-defaults-{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEMP_DB.as_posix()}"

from app_state_models import AppState  # noqa: E402
from app_state_service import (  # noqa: E402
    CAMERA_POSITION_STATE_KEY,
    camera_position_needs_default_seed,
    default_camera_position_config,
    read_app_state_value,
    save_app_state_value,
    seed_default_camera_position,
)
from database import Base, SessionLocal, engine  # noqa: E402
from schemas import CameraPositionConfig  # noqa: E402


class CameraPositionDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        try:
            TEMP_DB.unlink(missing_ok=True)
        except PermissionError:
            pass

    def setUp(self) -> None:
        with SessionLocal() as db:
            db.query(AppState).filter(AppState.state_key == CAMERA_POSITION_STATE_KEY).delete()
            db.commit()

    def test_schema_default_is_current_calibration(self) -> None:
        config = CameraPositionConfig()
        self.assertEqual(config.camera_height_mm, 150)
        self.assertEqual(config.pitch_down_deg, 20)
        self.assertGreater(config.fx, 0)
        self.assertGreater(config.fy, 0)
        self.assertTrue(config.calibrated)

    def test_missing_state_is_seeded(self) -> None:
        with SessionLocal() as db:
            seeded = seed_default_camera_position(db)
            saved = read_app_state_value(db, CAMERA_POSITION_STATE_KEY)

        self.assertIsNotNone(seeded)
        self.assertEqual(saved, default_camera_position_config())

    def test_legacy_or_uncalibrated_state_is_replaced(self) -> None:
        legacy = {
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
        }
        self.assertTrue(camera_position_needs_default_seed(legacy))
        self.assertTrue(camera_position_needs_default_seed({"fx": 0, "fy": 0}))
        self.assertTrue(camera_position_needs_default_seed({"fx": 1500, "fy": 1510}))

        with SessionLocal() as db:
            save_app_state_value(db, CAMERA_POSITION_STATE_KEY, legacy)
            seed_default_camera_position(db)
            saved = read_app_state_value(db, CAMERA_POSITION_STATE_KEY)

        self.assertEqual(saved, default_camera_position_config())

    def test_custom_valid_state_is_not_overwritten(self) -> None:
        custom = {
            **default_camera_position_config(),
            "fx": 1500,
            "fy": 1510,
            "yaw_deg": 2.5,
        }
        self.assertFalse(camera_position_needs_default_seed(custom))

        with SessionLocal() as db:
            save_app_state_value(db, CAMERA_POSITION_STATE_KEY, custom)
            seeded = seed_default_camera_position(db)
            saved = read_app_state_value(db, CAMERA_POSITION_STATE_KEY)

        self.assertIsNone(seeded)
        self.assertEqual(saved, custom)


if __name__ == "__main__":
    unittest.main()
