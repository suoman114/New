"""platform.eventbus 계약 테스트 — pub/sub, ring buffer, event_id 인덱스, 필터."""

import asyncio

from sim.platform.eventbus import EventBus
from sim.platform.models import FlowEvent


async def test_publish_index_and_get():
    bus = EventBus(ring_size=10)
    ev = await bus.publish(FlowEvent(session_id="s1", call_id="c1", label="INVITE"))
    assert bus.get(ev.event_id) is ev
    assert bus.get("nope") is None


async def test_recent_filtering():
    bus = EventBus(ring_size=100)
    await bus.publish(FlowEvent(session_id="s1", call_id="c1", channel="SIP", label="INVITE"))
    await bus.publish(FlowEvent(session_id="s1", call_id="c1", channel="RMQ", label="start_req"))
    await bus.publish(FlowEvent(session_id="s2", call_id="c2", channel="SIP", label="INVITE"))

    assert len(bus.recent()) == 3
    assert len(bus.recent(session_id="s1")) == 2
    assert len(bus.recent(call_id="c2")) == 1
    assert len(bus.recent(channel="RMQ")) == 1


async def test_ring_buffer_evicts_oldest():
    bus = EventBus(ring_size=3)
    ids = []
    for i in range(5):
        ev = await bus.publish(FlowEvent(session_id="s", label=f"e{i}"))
        ids.append(ev.event_id)
    recent = bus.recent()
    assert len(recent) == 3
    assert [e.label for e in recent] == ["e2", "e3", "e4"]


async def test_subscribe_receives_live_events():
    bus = EventBus()
    received: list[FlowEvent] = []

    async def consumer():
        async for ev in bus.subscribe():
            received.append(ev)
            if len(received) >= 2:
                break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.01)  # 구독 등록 대기
    await bus.publish(FlowEvent(label="a"))
    await bus.publish(FlowEvent(label="b"))
    await asyncio.wait_for(task, timeout=1.0)

    assert [e.label for e in received] == ["a", "b"]


async def test_subscribe_backfill():
    bus = EventBus()
    await bus.publish(FlowEvent(label="old1"))
    await bus.publish(FlowEvent(label="old2"))

    seen: list[str] = []

    async def consumer():
        async for ev in bus.subscribe(backfill=10):
            seen.append(ev.label)
            if ev.label == "live":
                break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.01)
    await bus.publish(FlowEvent(label="live"))
    await asyncio.wait_for(task, timeout=1.0)

    assert seen == ["old1", "old2", "live"]
