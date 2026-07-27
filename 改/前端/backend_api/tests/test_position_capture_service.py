from __future__ import annotations

import io
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from assistant_orchestrator import (  # noqa: E402
    _context_for_model,
    _deterministic_position_answer,
    _has_fresh_position_context,
    _is_high_confidence_position_request,
    _is_water_gun_spray_request,
)
from camera_service import BackendCameraService  # noqa: E402
from position_capture_service import (  # noqa: E402
    POSITION_CAPTURE_TTL_MS,
    read_position_capture,
)
from position_service import locate_object  # noqa: E402
from schemas import CameraPositionConfig  # noqa: E402


def jpeg_frame(width: int = 320, height: int = 180) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (236, 240, 232)).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


class PositionCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = CameraPositionConfig(
            image_width=320,
            image_height=180,
            fx=350,
            fy=350,
            cx=160,
            cy=90,
            camera_height_mm=110,
            pitch_down_deg=30,
        )

    def test_located_multiple_and_not_found_all_get_annotated_images(self) -> None:
        results = (
            {"detections": [{"label": "U盘", "confidence": 0.95, "bbox": {"x": 40, "y": 35, "width": 20, "height": 25}}]},
            {"detections": [
                {"label": "U盘", "confidence": 0.95, "bbox": {"x": 20, "y": 35, "width": 20, "height": 25}},
                {"label": "U盘", "confidence": 0.85, "bbox": {"x": 65, "y": 35, "width": 18, "height": 25}},
            ]},
            {"detections": []},
        )
        with tempfile.TemporaryDirectory() as folder, patch(
            "position_capture_service.POSITION_CAPTURE_ROOT", Path(folder)
        ):
            for index, vision_result in enumerate(results):
                captured_at = int(time.time() * 1000) + index
                with patch("position_service.call_object_locator", return_value=vision_result):
                    result = locate_object(jpeg_frame(), "image/jpeg", "U盘在哪", self.config, captured_at)
                self.assertEqual(result.captured_at, captured_at)
                self.assertEqual((result.image_width, result.image_height), (320, 180))
                self.assertTrue(result.annotated_image_url)
                capture_id = str(result.annotated_image_url).rsplit("/", 1)[-1].removesuffix(".jpg")
                image_bytes = read_position_capture(capture_id, captured_at)
                self.assertIsNotNone(image_bytes)
                self.assertGreater(len(image_bytes or b""), 500)
                if index == 0:
                    annotated = Image.open(io.BytesIO(image_bytes or b"")).convert("RGB")
                    red, green, blue = annotated.getpixel((160, 86))
                    self.assertGreater(red, green + 50)
                    self.assertGreater(red, blue + 50)
                    # The annotated image contains no title, height or confidence text.
                    corner = annotated.getpixel((12, 12))
                    self.assertTrue(all(channel > 210 for channel in corner))

    def test_position_capture_expires_after_24_hours(self) -> None:
        with tempfile.TemporaryDirectory() as folder, patch(
            "position_capture_service.POSITION_CAPTURE_ROOT", Path(folder)
        ):
            captured_at = int(time.time() * 1000)
            with patch("position_service.call_object_locator", return_value={"detections": []}):
                result = locate_object(jpeg_frame(), "image/jpeg", "U盘在哪", self.config, captured_at)
            capture_id = str(result.annotated_image_url).rsplit("/", 1)[-1].removesuffix(".jpg")
            path = Path(folder) / f"{capture_id}.jpg"
            expired_at = captured_at - POSITION_CAPTURE_TTL_MS - 1000
            os.utime(path, (expired_at / 1000, expired_at / 1000))
            self.assertIsNone(read_position_capture(capture_id, captured_at))
            self.assertFalse(path.exists())

    def test_fresh_snapshot_waits_for_next_frame_without_waking_camera(self) -> None:
        service = BackendCameraService()
        service._wake.clear()

        def publish_frame() -> None:
            time.sleep(0.05)
            with service._lock:
                service._jpeg = b"new-frame"
                service._captured_at = int(time.time() * 1000) + 5
                service._actual_width = 320
                service._actual_height = 180

        thread = threading.Thread(target=publish_frame)
        thread.start()
        snapshot = service.fresh_snapshot(timeout_seconds=1)
        thread.join(timeout=1)
        self.assertEqual(snapshot.jpeg, b"new-frame")
        self.assertFalse(service._wake.is_set())

    def test_old_geometry_is_hidden_and_contextual_refinement_requires_new_location(self) -> None:
        old_context = [{
            "position_result": {
                "status": "located",
                "result_id": "position-old",
                "selected": {"label": "U盘"},
                "candidates": [{
                    "label": "U盘",
                    "description": "银色金属外壳",
                    "attributes": {"color": "银色"},
                    "ground_range_mm": 229,
                    "bearing_deg": 3,
                }],
            },
            "camera_captured_at": 100,
        }]
        model_context = str(_context_for_model(old_context))
        self.assertNotIn("229", model_context)
        self.assertNotIn("ground_range_mm", model_context)
        self.assertIn("U盘", model_context)
        self.assertTrue(_is_high_confidence_position_request("银色的", old_context))
        self.assertFalse(_has_fresh_position_context(old_context[0], 100))

    def test_c5_position_answer_is_brief_and_spray_intent_is_explicit(self) -> None:
        context = {
            "position_result": {
                "status": "located",
                "selected": {
                    "label": "U盘",
                    "camera_range_mm": 1100,
                    "ground_range_mm": 1000,
                    "bearing_deg": -30,
                },
            }
        }
        answer = _deterministic_position_answer(context, "edge_text")
        self.assertEqual(answer, "U盘在前方 0.9 米，靠左 0.5 米。")
        self.assertTrue(_is_water_gun_spray_request("让水枪喷一下这个 U 盘"))
        self.assertFalse(_is_water_gun_spray_request("水枪现在在哪里"))


if __name__ == "__main__":
    unittest.main()
