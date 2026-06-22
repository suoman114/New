"""EventBus: asyncio 기반 pub/sub.

- 모든 엔진이 `publish(FlowEvent)` 로 발행한다.
- dashboard-backend 가 `subscribe()` 로 실시간 구독(WebSocket 중계).
- late-join 구독자를 위해 ring buffer(최근 N건) 백필을 제공한다.
- `event_id` 인덱스로 단건 조회(로그 드릴다운 상관).

다른 모든 엔진이 의존하므로 공개 API 시그니처를 안정적으로 유지한다 (CLAUDE.md §4.2-3).
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import AsyncIterator, Optional

from .models import FlowEvent


class EventBus:
    def __init__(self, ring_size: int = 5000) -> None:
        self._subscribers: set[asyncio.Queue[FlowEvent]] = set()
        self._ring: deque[FlowEvent] = deque(maxlen=ring_size)
        self._index: dict[str, FlowEvent] = {}
        self._lock = asyncio.Lock()

    async def publish(self, event: FlowEvent) -> FlowEvent:
        """이벤트를 ring buffer/인덱스에 보관하고 모든 구독자에게 전달한다."""
        self._ring.append(event)
        self._index[event.event_id] = event
        # ring 에서 밀려난 항목은 인덱스에서도 정리(메모리 누수 방지)
        if len(self._index) > self._ring.maxlen * 2:
            live = {e.event_id for e in self._ring}
            self._index = {k: v for k, v in self._index.items() if k in live}
        for q in list(self._subscribers):
            # 느린 구독자가 전체를 막지 않도록 best-effort
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event

    def get(self, event_id: str) -> Optional[FlowEvent]:
        """event_id 단건 조회 (로그 드릴다운 상관용)."""
        return self._index.get(event_id)

    def recent(self, limit: int = 200, *, session_id: str | None = None,
               call_id: str | None = None, channel: str | None = None) -> list[FlowEvent]:
        """최근 이벤트 조회(필터 가능). late-join 백필/REST 조회에 사용."""
        items = list(self._ring)
        if session_id is not None:
            items = [e for e in items if e.session_id == session_id]
        if call_id is not None:
            items = [e for e in items if e.call_id == call_id]
        if channel is not None:
            items = [e for e in items if e.channel == channel]
        return items[-limit:]

    async def subscribe(self, *, backfill: int = 0,
                        maxsize: int = 1000) -> AsyncIterator[FlowEvent]:
        """실시간 구독. backfill>0 이면 최근 이벤트를 먼저 흘려보낸다.

        사용:
            async for ev in bus.subscribe(backfill=100):
                ws.send(ev)
        """
        q: asyncio.Queue[FlowEvent] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(q)
        try:
            for ev in self.recent(limit=backfill) if backfill else []:
                yield ev
            while True:
                yield await q.get()
        finally:
            self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
