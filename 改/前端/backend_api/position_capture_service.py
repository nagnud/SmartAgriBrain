from __future__ import annotations

import io
import os
import re
import threading
import time
import uuid
from pathlib import Path

from PIL import Image, ImageDraw

from schemas import PositionCandidate, PositionLocateResponse


POSITION_CAPTURE_TTL_MS = 24 * 60 * 60 * 1000
POSITION_CAPTURE_ROOT = Path(
    os.getenv("POSITION_CAPTURE_ROOT", str(Path(__file__).resolve().parent / "position_captures"))
)
_CAPTURE_ID_PATTERN = re.compile(r"^capture-[0-9a-f]{32}$")
_capture_lock = threading.Lock()


def now_ms() -> int:
    return int(time.time() * 1000)


def ensure_position_capture_root() -> None:
    POSITION_CAPTURE_ROOT.mkdir(parents=True, exist_ok=True)


def cleanup_expired_position_captures(current_ms: int | None = None) -> int:
    ensure_position_capture_root()
    cutoff_ms = int(current_ms or now_ms()) - POSITION_CAPTURE_TTL_MS
    removed = 0
    with _capture_lock:
        for path in POSITION_CAPTURE_ROOT.glob("capture-*.jpg"):
            try:
                if int(path.stat().st_mtime * 1000) < cutoff_ms:
                    path.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                continue
    return removed


def _pixel_box(candidate: PositionCandidate, width: int, height: int) -> tuple[int, int, int, int]:
    bbox = candidate.bbox
    left = max(0, min(width - 1, round(float(bbox.get("x", 0)) * width / 100)))
    top = max(0, min(height - 1, round(float(bbox.get("y", 0)) * height / 100)))
    right = max(left + 1, min(width, round((float(bbox.get("x", 0)) + float(bbox.get("width", 0))) * width / 100)))
    bottom = max(top + 1, min(height, round((float(bbox.get("y", 0)) + float(bbox.get("height", 0))) * height / 100)))
    return left, top, right, bottom


def save_position_capture(
    image_bytes: bytes,
    result: PositionLocateResponse,
    captured_at: int,
) -> tuple[str | None, int, int]:
    """Render and persist the exact frame used for a positioning result."""
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None, 0, 0

    width, height = image.size
    draw = ImageDraw.Draw(image)
    line_width = max(3, round(min(width, height) / 180))

    for candidate in result.candidates:
        left, top, right, bottom = _pixel_box(candidate, width, height)
        color = (35, 155, 80)
        draw.rectangle((left, top, right, bottom), outline=color, width=line_width)
        contact_x = round(float(candidate.anchor.get("x", 0)) * width / 100)
        contact_y = round(float(candidate.anchor.get("y", 0)) * height / 100)
        contact_x = max(left, min(right, contact_x))
        contact_y = max(top, min(bottom, contact_y))
        radius = max(6, line_width * 2)
        draw.ellipse(
            (contact_x - radius, contact_y - radius, contact_x + radius, contact_y + radius),
            fill=(225, 48, 48),
            outline=(255, 255, 255),
            width=max(2, line_width // 2),
        )

    capture_id = f"capture-{uuid.uuid4().hex}"
    ensure_position_capture_root()
    cleanup_expired_position_captures(captured_at)
    destination = POSITION_CAPTURE_ROOT / f"{capture_id}.jpg"
    temporary = POSITION_CAPTURE_ROOT / f".{capture_id}.tmp"
    with _capture_lock:
        image.save(temporary, format="JPEG", quality=90, optimize=True)
        os.utime(temporary, (captured_at / 1000, captured_at / 1000))
        temporary.replace(destination)
    return f"/api/v1/position-captures/{capture_id}.jpg", width, height


def read_position_capture(capture_id: str, current_ms: int | None = None) -> bytes | None:
    if not _CAPTURE_ID_PATTERN.fullmatch(capture_id):
        return None
    current = int(current_ms or now_ms())
    path = POSITION_CAPTURE_ROOT / f"{capture_id}.jpg"
    try:
        modified_ms = int(path.stat().st_mtime * 1000)
    except OSError:
        return None
    if modified_ms + POSITION_CAPTURE_TTL_MS < current:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


class PositionCaptureCleanupRuntime:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="position-capture-cleanup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(60 * 60):
            cleanup_expired_position_captures()


position_capture_cleanup_runtime = PositionCaptureCleanupRuntime()
