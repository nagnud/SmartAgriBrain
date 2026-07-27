from __future__ import annotations

import logging
import os
import threading

from database import SessionLocal
from monitoring_service import check_offline_devices


logger = logging.getLogger("device-monitor")


class DeviceMonitorRuntime:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if os.getenv("DEVICE_MONITOR_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="device-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        interval = max(5, int(os.getenv("DEVICE_MONITOR_INTERVAL_SECONDS", "30")))
        while not self._stop_event.wait(interval):
            try:
                with SessionLocal() as db:
                    check_offline_devices(db)
            except Exception:
                logger.exception("设备在线状态检查暂时失败")


device_monitor_runtime = DeviceMonitorRuntime()
