from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from collections.abc import Generator
from typing import Any


class SiteEventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[queue.Queue[dict[str, Any]]]] = {}

    def publish(self, site_id: str, event_type: str, data: Any) -> None:
        event = {
            "id": str(uuid.uuid4()),
            "event": event_type,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with self._lock:
            subscribers = tuple(self._subscribers.get(site_id, set()))
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:
                try:
                    subscriber.get_nowait()
                    subscriber.put_nowait(event)
                except (queue.Empty, queue.Full):
                    pass

    def stream(self, site_id: str) -> Generator[str, None, None]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.setdefault(site_id, set()).add(subscriber)
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    event = subscriber.get(timeout=15)
                    payload = json.dumps(event["data"], ensure_ascii=False, separators=(",", ":"))
                    yield f'id: {event["id"]}\nevent: {event["event"]}\ndata: {payload}\n\n'
                except queue.Empty:
                    yield ": heartbeat\n\n"
        finally:
            with self._lock:
                subscribers = self._subscribers.get(site_id)
                if subscribers is not None:
                    subscribers.discard(subscriber)
                    if not subscribers:
                        self._subscribers.pop(site_id, None)


site_event_bus = SiteEventBus()
