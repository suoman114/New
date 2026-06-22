"""dashboard-backend 테스트 — REST(시나리오/이벤트/결과/드릴다운) + WebSocket."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.state import AppState


class CollectingFeeder:
    async def send_sip(self, data, *, event=None, session_id="", call_id="", label="SIP"):
        pass

    async def send_rtp(self, packet, port, *, session_id="", call_id=""):
        pass


@pytest.fixture()
def client() -> TestClient:
    state = AppState(feeder_factory=CollectingFeeder)
    return TestClient(create_app(state))


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_list_scenarios(client):
    data = client.get("/api/scenarios").json()
    ids = {s["id"] for s in data}
    assert "MCPTT-GROUP-FLOOR" in ids


def test_run_wait_and_sessions(client):
    r = client.post("/api/run", json={"scenario_id": "MCPTT-GROUP-FLOOR", "wait": True})
    assert r.status_code == 200
    sid = r.json()["session_ids"][0]

    sessions = client.get("/api/sessions").json()
    me = next(s for s in sessions if s["session_id"] == sid)
    assert me["state"] == "DONE"
    assert me["call_id"]

    detail = client.get(f"/api/sessions/{sid}").json()
    assert detail["run"]["service_type"] == "MCPTT"
    assert len(detail["run"]["spurts"]) == 3
    assert detail["run"]["expectations"]["rmq_change_sequence"] == ["TAKEN", "IDLE"] * 3


def test_unknown_scenario_404(client):
    r = client.post("/api/run", json={"scenario_id": "NOPE", "wait": True})
    assert r.status_code == 404


def test_events_and_log_drilldown(client):
    client.post("/api/run", json={"scenario_id": "MCPTT-GROUP-FLOOR", "wait": True})
    events = client.get("/api/events", params={"limit": 500}).json()
    assert len(events) > 0
    # SYS 시작 이벤트는 로그가 태깅됨 → 드릴다운에 로그 라인 존재
    sys_events = [e for e in events if e["channel"] == "SYS" and "start" in e["label"]]
    assert sys_events
    eid = sys_events[0]["event_id"]
    logs = client.get(f"/api/events/{eid}/logs").json()
    assert logs["event_id"] == eid
    assert any("MCPTT" in ln["message"] for ln in logs["logs"])


def test_events_filter_by_channel(client):
    client.post("/api/run", json={"scenario_id": "MCPTT-GROUP-FLOOR", "wait": True})
    rmq = client.get("/api/events", params={"channel": "RMQ", "limit": 500}).json()
    assert rmq and all(e["channel"] == "RMQ" for e in rmq)
    labels = [e["label"] for e in rmq]
    assert labels.count("floor TAKEN") == 3


def test_metrics(client):
    client.post("/api/run", json={"scenario_id": "MCPTT-GROUP-FLOOR", "wait": True})
    m = client.get("/api/metrics").json()
    assert m["sessions_total"] >= 1
    assert m["by_state"].get("DONE", 0) >= 1


def test_ws_flow_backfill(client):
    client.post("/api/run", json={"scenario_id": "MCPTT-GROUP-FLOOR", "wait": True})
    with client.websocket_connect("/ws/flow?backfill=50") as ws:
        first = ws.receive_json()
        assert "event_id" in first and "channel" in first
