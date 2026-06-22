"""RTP 송출 페이싱 (20ms frame 간격).

지터/burst 는 rtp.impair.jitter_schedule 값을 반영한다. 실제 송신은 udp_sender 가 수행하고,
여기서는 스케줄에 맞춰 await sleep 하는 페이서를 제공한다.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Iterable, TypeVar

T = TypeVar("T")


async def pace(items: Iterable[T], schedule_ms: list[float]) -> AsyncIterator[T]:
    """schedule_ms[i] 누적 시각에 맞춰 item 을 하나씩 내보낸다."""
    loop = asyncio.get_event_loop()
    start = loop.time()
    for i, item in enumerate(items):
        target = start + (schedule_ms[i] / 1000.0 if i < len(schedule_ms) else 0.0)
        delay = target - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        yield item


async def pace_fixed(items: Iterable[T], interval_ms: int = 20) -> AsyncIterator[T]:
    """고정 간격 페이싱."""
    first = True
    for item in items:
        if not first:
            await asyncio.sleep(interval_ms / 1000.0)
        first = False
        yield item
