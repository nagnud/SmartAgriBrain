from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Generator


@dataclass(frozen=True)
class CameraSnapshot:
    jpeg: bytes
    captured_at: int
    width: int
    height: int


class BackendCameraService:
    """Own the USB camera once and share fresh JPEG frames with every channel."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._jpeg = b""
        self._captured_at = 0
        self._actual_width = 0
        self._actual_height = 0
        self._connected = False
        self._error = ""
        self._index = int(os.getenv("CAMERA_DEVICE_INDEX", "0"))
        self._width = int(os.getenv("CAMERA_WIDTH", "1280"))
        self._height = int(os.getenv("CAMERA_HEIGHT", "720"))
        self._fps = max(1, min(30, int(os.getenv("CAMERA_FPS", "15"))))

    def configure(self, index: int, width: int, height: int, fps: int = 15) -> None:
        with self._lock:
            changed = (index, width, height, fps) != (self._index, self._width, self._height, self._fps)
            self._index = max(0, min(20, int(index)))
            self._width = max(160, min(7680, int(width)))
            self._height = max(120, min(4320, int(height)))
            self._fps = max(1, min(30, int(fps)))
            if changed:
                self._jpeg = b""
                self._captured_at = 0
                self._connected = False
        if changed:
            self._wake.set()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="backend-usb-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=3)
        self._thread = None

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "connected": self._connected,
                "device_index": self._index,
                "configured_width": self._width,
                "configured_height": self._height,
                "width": self._actual_width,
                "height": self._actual_height,
                "fps": self._fps,
                "captured_at": self._captured_at,
                "error": self._error,
            }

    def snapshot(self, max_age_ms: int = 1500) -> CameraSnapshot:
        """Return a recent shared preview frame.

        This is appropriate for the live preview.  Measurement paths must use
        ``fresh_snapshot`` instead: a recent preview is not evidence that the
        object is still at the same location.
        """
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            with self._lock:
                age = int(time.time() * 1000) - self._captured_at
                if self._jpeg and age <= max_age_ms:
                    return CameraSnapshot(self._jpeg, self._captured_at, self._actual_width, self._actual_height)
                error = self._error
            self._wake.set()
            time.sleep(0.05)
        raise RuntimeError(error or "摄像头暂时没有可用画面。")

    def fresh_snapshot(self, timeout_seconds: float = 3.0, after_captured_at: int | None = None) -> CameraSnapshot:
        """Wait for a frame captured after this request began.

        A positioning result is a measurement, so it must never be calculated
        from the short-lived preview cache returned by ``snapshot``.  The
        capture thread continuously reads the camera; waiting for a timestamp
        newer than the call start guarantees that every positioning request
        uses a newly captured image, including rapid consecutive questions.
        """
        requested_at = max(int(time.time() * 1000), int(after_captured_at or 0))
        deadline = time.monotonic() + max(0.1, timeout_seconds)
        while time.monotonic() < deadline:
            with self._lock:
                if self._jpeg and self._captured_at > requested_at:
                    return CameraSnapshot(self._jpeg, self._captured_at, self._actual_width, self._actual_height)
                error = self._error
            time.sleep(0.02)
        raise RuntimeError(error or "摄像头没有取得新的画面，请检查连接后重试。")

    def mjpeg_stream(self) -> Generator[bytes, None, None]:
        previous_timestamp = -1
        while not self._stop.is_set():
            with self._lock:
                jpeg = self._jpeg
                timestamp = self._captured_at
            if jpeg and timestamp != previous_timestamp:
                previous_timestamp = timestamp
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\nCache-Control: no-cache\r\n\r\n"
                    + jpeg
                    + b"\r\n"
                )
            time.sleep(0.04)

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._connected = False
            self._error = message[:300]

    def _run(self) -> None:
        try:
            import cv2  # type: ignore
        except Exception as error:
            self._set_error(f"摄像头组件不可用：{error}")
            return

        capture = None
        active_config: tuple[int, int, int, int] | None = None
        try:
            while not self._stop.is_set():
                with self._lock:
                    config = (self._index, self._width, self._height, self._fps)
                if self._wake.is_set():
                    self._wake.clear()
                if capture is None or active_config != config:
                    if capture is not None:
                        capture.release()
                    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
                    capture = cv2.VideoCapture(config[0], backend)
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, config[1])
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config[2])
                    capture.set(cv2.CAP_PROP_FPS, config[3])
                    active_config = config
                    if not capture.isOpened():
                        self._set_error(f"无法打开摄像头 {config[0]}，请检查设备是否被其他程序占用。")
                        capture.release()
                        capture = None
                        self._stop.wait(1.5)
                        continue

                ok, frame = capture.read()
                if not ok or frame is None:
                    self._set_error("摄像头读取失败，正在重新连接。")
                    capture.release()
                    capture = None
                    self._stop.wait(0.5)
                    continue
                encoded, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
                if not encoded:
                    continue
                height, width = frame.shape[:2]
                with self._lock:
                    self._jpeg = buffer.tobytes()
                    self._captured_at = int(time.time() * 1000)
                    self._actual_width = int(width)
                    self._actual_height = int(height)
                    self._connected = True
                    self._error = ""
                self._stop.wait(1.0 / config[3])
        finally:
            if capture is not None:
                capture.release()


camera_service = BackendCameraService()
