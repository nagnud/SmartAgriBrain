from __future__ import annotations

import math
import sys
import unittest
from unittest.mock import patch
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from position_service import build_position_prompt, PixelDetection, locate_from_vision_result, project_to_ground  # noqa: E402
from schemas import CameraPositionConfig  # noqa: E402


class PositionServiceTests(unittest.TestCase):
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
            yaw_deg=0,
            roll_deg=0,
        )

    def test_center_ray_intersects_ground_in_front(self) -> None:
        candidate = project_to_ground(PixelDetection("calibration", 0.9, 49.0, 49.0, 2.0, 2.0), self.config)
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertAlmostEqual(candidate.ground_range_mm, 103.9, delta=1.0)
        self.assertAlmostEqual(candidate.bearing_deg, 0.0, delta=1.0)
        self.assertGreater(candidate.camera_range_mm, candidate.ground_range_mm)

    def test_right_side_target_has_positive_bearing(self) -> None:
        candidate = project_to_ground(PixelDetection("苹果", 0.9, 70.0, 49.0, 4.0, 2.0), self.config)
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertGreater(candidate.bearing_deg, 0)

    def test_ai_anchor_and_reliable_height_drive_projection(self) -> None:
        ground_anchor = PixelDetection(
            "杯子",
            0.95,
            40,
            40,
            20,
            20,
            anchor_x=50,
            anchor_y=50,
            anchor_type="visual_center",
            estimated_height_mm=0,
            height_confidence=0.95,
            anchor_reason="使用杯子中心",
            height_estimate_provided=True,
        )
        raised_anchor = PixelDetection(
            "杯子",
            0.95,
            40,
            40,
            20,
            20,
            anchor_x=50,
            anchor_y=50,
            anchor_type="visual_center",
            estimated_height_mm=20,
            height_confidence=0.9,
            anchor_reason="中心约离桌面20毫米",
            height_estimate_provided=True,
        )
        ground = project_to_ground(ground_anchor, self.config)
        raised = project_to_ground(raised_anchor, self.config)
        self.assertIsNotNone(ground)
        self.assertIsNotNone(raised)
        assert ground is not None and raised is not None
        self.assertFalse(raised.height_fallback)
        self.assertEqual(raised.effective_height_mm, 20)
        self.assertLess(raised.ground_range_mm, ground.ground_range_mm)

    def test_fruit_targets_use_ground_footprint_even_when_ai_marks_center(self) -> None:
        fruit_anchor = PixelDetection(
            "apple",
            0.95,
            40,
            40,
            20,
            20,
            anchor_x=50,
            anchor_y=50,
            anchor_type="surface_center",
            estimated_height_mm=20,
            height_confidence=0.9,
            anchor_reason="apple center is above the table",
            height_estimate_provided=True,
        )
        footprint_anchor = PixelDetection(
            "calibration",
            0.95,
            40,
            40,
            20,
            20,
            anchor_x=50,
            anchor_y=60,
            anchor_type="footprint_center",
            estimated_height_mm=0,
            height_confidence=0.9,
            height_estimate_provided=True,
        )
        fruit = project_to_ground(fruit_anchor, self.config)
        footprint = project_to_ground(footprint_anchor, self.config)
        self.assertIsNotNone(fruit)
        self.assertIsNotNone(footprint)
        assert fruit is not None and footprint is not None
        self.assertEqual(fruit.anchor, {"x": 50, "y": 60})
        self.assertEqual(fruit.anchor_type, "footprint_center")
        self.assertTrue(fruit.height_fallback)
        self.assertEqual(fruit.effective_height_mm, 0)
        self.assertAlmostEqual(fruit.ground_range_mm, footprint.ground_range_mm, delta=0.1)

    def test_chinese_pear_ignores_ai_center_anchor_for_ground_footprint(self) -> None:
        pear = PixelDetection(
            "\u68a8",
            0.95,
            48,
            8,
            4,
            6,
            anchor_x=50,
            anchor_y=11,
            anchor_type="visual_center",
            estimated_height_mm=40,
            height_confidence=0.9,
            height_estimate_provided=True,
        )
        candidate = project_to_ground(pear, CameraPositionConfig())
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.anchor_type, "footprint_center")
        self.assertEqual(candidate.anchor, {"x": 50.0, "y": 14})
        self.assertEqual(candidate.effective_height_mm, 0)
        self.assertGreater(candidate.ground_range_mm, 700)

    def test_unreliable_or_impossible_height_falls_back_to_ground(self) -> None:
        baseline = project_to_ground(
            PixelDetection("瓶子", 0.9, 40, 40, 20, 20),
            self.config,
        )
        for height, confidence in ((40, 0.2), (500, 0.95)):
            candidate = project_to_ground(
                PixelDetection(
                    "瓶子",
                    0.9,
                    40,
                    40,
                    20,
                    20,
                    anchor_x=50,
                    anchor_y=50,
                    estimated_height_mm=height,
                    height_confidence=confidence,
                    height_estimate_provided=True,
                ),
                self.config,
            )
            self.assertIsNotNone(candidate)
            assert candidate is not None and baseline is not None
            self.assertTrue(candidate.height_fallback)
            self.assertEqual(candidate.effective_height_mm, 0)
            self.assertAlmostEqual(candidate.ground_range_mm, baseline.ground_range_mm, delta=0.1)

    def test_ai_selected_pixel_replaces_bbox_center(self) -> None:
        candidate = project_to_ground(
            PixelDetection(
                "长尺",
                0.9,
                30,
                40,
                40,
                20,
                anchor_x=62,
                anchor_y=50,
                anchor_type="custom",
                estimated_height_mm=0,
                height_confidence=0.9,
                height_estimate_provided=True,
            ),
            self.config,
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.anchor, {"x": 62.0, "y": 50.0})
        self.assertGreater(candidate.bearing_deg, 0)

    def test_three_field_calibration_points(self) -> None:
        config = CameraPositionConfig(
            image_width=1280,
            image_height=720,
            fx=1288,
            fy=1288,
            cx=640,
            cy=358,
            camera_height_mm=110,
            pitch_down_deg=30,
        )
        for pixel_v, expected_mm in ((720, 108), (491, 150), (220, 250)):
            height_pct = 1.0
            detection = PixelDetection(
                "标定点",
                1.0,
                49.0,
                pixel_v / 720 * 100 - height_pct / 2,
                2.0,
                height_pct,
            )
            candidate = project_to_ground(detection, config)
            self.assertIsNotNone(candidate)
            assert candidate is not None
            self.assertAlmostEqual(candidate.ground_range_mm, expected_mm, delta=3.0)

    def test_three_polar_field_points(self) -> None:
        config = CameraPositionConfig(
            image_width=1280,
            image_height=720,
            fx=1394,
            fy=1394,
            cx=640,
            cy=349,
            camera_height_mm=110,
            pitch_down_deg=30,
            yaw_deg=-1.1,
            roll_deg=-0.13,
        )
        field_points = (
            (288.2, 435.6, 172.5, -18.0),
            (584.0, 259.4, 223.0, -3.5),
            (918.3, 418.3, 175.0, 12.0),
        )
        for pixel_u, pixel_v, expected_range, expected_bearing in field_points:
            width_pct = 1.0
            height_pct = 1.0
            detection = PixelDetection(
                "标定点",
                1.0,
                pixel_u / 1280 * 100 - width_pct / 2,
                pixel_v / 720 * 100 - height_pct / 2,
                width_pct,
                height_pct,
            )
            candidate = project_to_ground(detection, config)
            self.assertIsNotNone(candidate)
            assert candidate is not None
            self.assertAlmostEqual(candidate.ground_range_mm, expected_range, delta=1.0)
            self.assertAlmostEqual(candidate.bearing_deg, expected_bearing, delta=0.4)

    def test_default_camera_position_uses_current_floor_calibration(self) -> None:
        config = CameraPositionConfig()
        self.assertEqual(config.camera_height_mm, 150)
        self.assertEqual(config.pitch_down_deg, 15)
        self.assertGreater(config.fx, 0)
        self.assertGreater(config.fy, 0)

        field_points = (
            (629.0, 475.4, 400.0, 0.0),
            (637.3, 261.9, 700.0, 0.0),
            (664.7, 163.3, 1000.0, 0.0),
            (676.5, 127.8, 1200.0, 0.0),
        )
        for pixel_u, pixel_v, expected_forward, expected_right in field_points:
            width_pct = 1.0
            height_pct = 1.0
            detection = PixelDetection(
                "calibration",
                1.0,
                pixel_u / 1280 * 100 - width_pct / 2,
                pixel_v / 720 * 100 - height_pct / 2,
                width_pct,
                height_pct,
            )
            candidate = project_to_ground(detection, config)
            self.assertIsNotNone(candidate)
            assert candidate is not None
            bearing_rad = math.radians(candidate.bearing_deg)
            actual_forward = candidate.ground_range_mm * math.cos(bearing_rad)
            actual_right = candidate.ground_range_mm * math.sin(bearing_rad)
            self.assertAlmostEqual(actual_forward, expected_forward, delta=70.0)
            self.assertAlmostEqual(actual_right, expected_right, delta=70.0)

    def test_missing_intrinsics_never_returns_location(self) -> None:
        result = locate_from_vision_result(
            "苹果多远",
            {"detections": [{"label": "苹果", "confidence": 0.9, "bbox": {"x": 45, "y": 45, "width": 10, "height": 10}}]},
            CameraPositionConfig(fx=0, fy=0),
        )
        self.assertEqual(result.status, "calibration_missing")

    def test_prompt_requires_specific_fruit_labels(self) -> None:
        prompt = build_position_prompt("画面里有什么水果")
        self.assertIn("具体水果名", prompt)
        self.assertIn("不要只写“水果”", prompt)
        self.assertIn("苹果、梨", prompt)

    def test_multiple_detections_require_user_disambiguation(self) -> None:
        result = locate_from_vision_result(
            "苹果多远",
            {"detections": [
                {"label": "苹果", "confidence": 0.9, "bbox": {"x": 45, "y": 45, "width": 10, "height": 10}},
                {"label": "苹果", "confidence": 0.8, "bbox": {"x": 60, "y": 45, "width": 10, "height": 10}},
            ]},
            self.config,
        )
        self.assertEqual(result.status, "multiple")
        self.assertEqual(len(result.candidates), 2)

    def test_named_fruit_selects_matching_candidate(self) -> None:
        result = locate_from_vision_result(
            "朝苹果喷水",
            {"detections": [
                {"label": "梨", "confidence": 0.9, "bbox": {"x": 35, "y": 45, "width": 10, "height": 10}},
                {"label": "苹果", "confidence": 0.9, "bbox": {"x": 55, "y": 45, "width": 10, "height": 10}},
            ]},
            self.config,
        )
        self.assertEqual(result.status, "located")
        self.assertIsNotNone(result.selected)
        assert result.selected is not None
        self.assertEqual(result.selected.label, "苹果")

    def test_generic_fruit_lists_specific_candidates(self) -> None:
        result = locate_from_vision_result(
            "画面里有什么水果",
            {"detections": [
                {"label": "梨", "confidence": 0.9, "bbox": {"x": 35, "y": 45, "width": 10, "height": 10}},
                {"label": "苹果", "confidence": 0.9, "bbox": {"x": 55, "y": 45, "width": 10, "height": 10}},
            ]},
            self.config,
        )
        self.assertEqual(result.status, "multiple")
        self.assertIn("梨、苹果", result.message)

    def test_left_qualifier_selects_left_candidate(self) -> None:
        result = locate_from_vision_result(
            "左边那个苹果多远",
            {"detections": [
                {"label": "苹果", "confidence": 0.9, "bbox": {"x": 25, "y": 45, "width": 10, "height": 10}},
                {"label": "苹果", "confidence": 0.8, "bbox": {"x": 65, "y": 45, "width": 10, "height": 10}},
            ]},
            self.config,
        )
        self.assertEqual(result.status, "located")
        self.assertIsNotNone(result.selected)
        assert result.selected is not None
        self.assertLess(result.selected.bbox["x"], 50)

    def test_empty_vision_result_is_not_found(self) -> None:
        result = locate_from_vision_result("苹果多远", {"detections": []}, self.config)
        self.assertEqual(result.status, "not_found")

    def test_locator_vision_result_can_be_stubbed_without_network(self) -> None:
        with patch("position_service.call_object_locator", return_value={"detections": [
            {"label": "苹果", "confidence": 0.91, "bbox": {"x": 45, "y": 45, "width": 10, "height": 10}},
        ]}):
            from position_service import locate_object
            result = locate_object(b"jpeg", "image/jpeg", "苹果多远", self.config)
        self.assertEqual(result.status, "located")
        self.assertTrue(result.result_id)


if __name__ == "__main__":
    unittest.main()
