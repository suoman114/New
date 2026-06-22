"""platform.logging 계약 테스트 — event_id 태깅 로그 드릴다운 저장소."""

from sim.platform.logging import LogStore, log_for
from sim.platform.models import FlowEvent


def test_log_for_stores_under_event_id():
    store = LogStore()
    ev = FlowEvent(session_id="s1", call_id="c1", label="INVITE")
    log_for(ev, "sent INVITE to VCSM", store=store)
    log_for(ev, "200 OK received", level="info", store=store)

    lines = store.get(ev.event_id)
    assert len(lines) == 2
    assert lines[0].message == "sent INVITE to VCSM"
    assert lines[0].session_id == "s1"
    assert lines[0].call_id == "c1"


def test_log_store_lru_event_cap():
    store = LogStore(max_events=2)
    evs = [FlowEvent(label=f"e{i}") for i in range(3)]
    for ev in evs:
        log_for(ev, "x", store=store)
    # 가장 오래된 event 는 밀려난다
    assert store.get(evs[0].event_id) == []
    assert len(store.get(evs[1].event_id)) == 1
    assert len(store.get(evs[2].event_id)) == 1


def test_log_store_lines_per_event_cap():
    store = LogStore(max_lines_per_event=3)
    ev = FlowEvent(label="e")
    for i in range(10):
        log_for(ev, f"line{i}", store=store)
    assert len(store.get(ev.event_id)) == 3
