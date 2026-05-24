"""In-memory pub/sub for inspection events (SSE)."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import settings


class EventBus:
    """Per-line ring buffer + async subscribers."""

    def __init__(self) -> None:
        self._buffers: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=settings.event_buffer_size)
        )
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def publish(self, line_id: str, payload: dict[str, Any]) -> None:
        self._buffers[line_id].append(payload)
        for q in list(self._subscribers.get(line_id, ())):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def recent(self, line_id: str) -> list[dict[str, Any]]:
        return list(self._buffers.get(line_id, ()))

    async def subscribe(self, line_id: str) -> AsyncIterator[str]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._subscribers[line_id].add(q)
        try:
            for buffered in self.recent(line_id):
                yield _sse(buffered)
            while True:
                payload = await q.get()
                yield _sse(payload)
        finally:
            self._subscribers[line_id].discard(q)


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


bus = EventBus()
