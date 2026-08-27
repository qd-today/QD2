"""In-memory log stream manager for real-time task execution logs.

Per-user pub/sub: scheduler publishes events, WebSocket clients subscribe.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("qd2.logstream")

MAX_BUFFER = 200  # keep last N events per user for late joiners


class LogStreamManager:
    """Fan-out log events to connected WebSocket clients, per user."""

    def __init__(self) -> None:
        self._queues: dict[int, set[asyncio.Queue]] = {}
        self._buffers: dict[int, list[dict]] = {}

    def subscribe(self, user_id: int, max_queue_size: int = 100) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._queues.setdefault(user_id, set()).add(q)
        return q

    def unsubscribe(self, user_id: int, q: asyncio.Queue) -> None:
        self._queues.get(user_id, set()).discard(q)

    def buffer(self, user_id: int) -> list[dict]:
        return list(self._buffers.get(user_id, []))

    def publish(self, user_id: int, event_type: str, **data: Any) -> None:
        """Publish an event to all subscribers of a user (non-blocking)."""
        event = {
            "type": event_type,
            "time": datetime.now().strftime("%H:%M:%S"),
            **data,
        }
        buf = self._buffers.setdefault(user_id, [])
        buf.append(event)
        if len(buf) > MAX_BUFFER:
            del buf[: len(buf) - MAX_BUFFER]

        for q in self._queues.get(user_id, set()):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow client; drop


log_stream = LogStreamManager()
