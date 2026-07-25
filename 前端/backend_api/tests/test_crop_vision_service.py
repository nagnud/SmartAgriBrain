from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

TEMP_DB = Path(tempfile.gettempdir()) / f"crop-vision-test-{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEMP_DB.as_posix()}"

from crop_vision_service import detect_current_crop_positions, read_current_crop_positions, save_current_crop_positions  # noqa: E402
from database import SessionLocal, engine, init_database  # noqa: E402
from schemas import CameraPositionConfig  # noqa: E402


class CropVisionServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        init_database()

    @classmethod
    def tearDownClass(cls) -> None:
        engine.dispose()
        try:
            TEMP_DB.unlink(missing_ok=True)
        except PermissionError:
            pass

    def setUp(self) -> None:
        self.config = CameraPositionConfig(
            image_width=1280,
            image_height=720,
            fx=1000,
            fy=1000,
            cx=640,
            cy=360,
            camera_height_mm=60,
            pitch_down_deg=30,
        )

    def test_empty_or_non_crop_result_overwrites_current_state(self) -> None:
        with SessionLocal() as db:
            with patch("crop_vision_service._call_crop_detector", return_value={"crops": [
                {
                    "label": "番茄",
                    "confidence": 0.9,
                    "bbox": {"x": 45, "y": 45, "width": 10, "height": 10},
                    "anchor": {"x": 50, "y": 50},
                    "clear_enough": True,
                    "growth_status": "长势正常",
                    "pest_disease_status": "未见明显病虫害",
                    "severity": "healthy",
                    "summary": "番茄长势正常",
                }
            ]}):
                first = detect_current_crop_positions(b"jpeg", "image/jpeg", self.config)
                save_current_crop_positions(db, first)
            self.assertEqual(len(read_current_crop_positions(db).crops), 1)

            with patch("crop_vision_service._call_crop_detector", return_value={"crops": []}):
                second = detect_current_crop_positions(b"jpeg", "image/jpeg", self.config)
                save_current_crop_positions(db, second)
            stored = read_current_crop_positions(db)
            self.assertEqual(stored.crops, [])

    def test_clear_crop_gets_growth_fields_and_water_gun_coordinates(self) -> None:
        with patch("crop_vision_service._call_crop_detector", return_value={"crops": [
            {
                "label": "黄瓜",
                "crop_name": "黄瓜",
                "confidence": 0.88,
                "bbox": {"x": 45, "y": 45, "width": 10, "height": 10},
                "anchor": {"x": 50, "y": 50},
                "clear_enough": True,
                "growth_status": "叶色正常",
                "pest_disease_status": "未见明显病虫害",
                "severity": "healthy",
                "summary": "黄瓜叶色正常",
            }
        ]}):
            result = detect_current_crop_positions(b"jpeg", "image/jpeg", self.config)
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.crops), 1)
        crop = result.crops[0]
        self.assertEqual(crop.crop_name, "黄瓜")
        self.assertEqual(crop.coordinate_status, "located")
        self.assertIsNotNone(crop.ground_range_mm)
        self.assertIsNotNone(crop.bearing_deg)
        self.assertEqual(crop.growth_status, "叶色正常")
        self.assertEqual(crop.pest_disease_status, "未见明显病虫害")

    def test_missing_calibration_keeps_crop_but_drops_coordinates(self) -> None:
        with patch("crop_vision_service._call_crop_detector", return_value={"crops": [
            {
                "label": "生菜",
                "confidence": 0.92,
                "bbox": {"x": 45, "y": 45, "width": 10, "height": 10},
                "anchor": {"x": 50, "y": 50},
                "clear_enough": False,
            }
        ]}):
            result = detect_current_crop_positions(b"jpeg", "image/jpeg", CameraPositionConfig())
        self.assertEqual(result.status, "calibration_missing")
        self.assertEqual(len(result.crops), 1)
        crop = result.crops[0]
        self.assertEqual(crop.coordinate_status, "calibration_missing")
        self.assertIsNone(crop.ground_range_mm)
        self.assertIsNone(crop.bearing_deg)
        self.assertIn("不够清晰", crop.summary)


if __name__ == "__main__":
    unittest.main()
