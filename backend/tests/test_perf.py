"""perf 테스트 — 메트릭 집계, ramp-up 부하 생성, perf 이벤트, /api/perf."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.state import AppState
from sim.perf import LoadGenerator, LoadSpec, PerfReport, PerfSample, perf_flow_event
from sim.perf.loadgen import make_default_runner
from sim.scenario.loader import Scenario
from sim.tapper.port_alloc import RtpPortAllocator


class CollectingFeeder:
    async def send_sip(self, data, *, event=None, session_id="", call_id="", label="SIP"):
        pass

    async def send_rtp(self, packet, port, *, session_id="", call_id=""):
        pass


def _scenario() -> Scenario:
    return Scenario.model_validate({
        "id": "T", "service_type": "MCPTT",
        "media": {"mode_set": [8], "pt": 98},
        "mcptt": {"group_id": "98152020001", "members": [{"mdn": "tel:+82585102802"}]},
        "floor_sequence": [{"talker": "tel:+82585102802", "duration_sec": 0.1}],
    })


# ── 메트릭 ──
def test_perf_report_summary_percentiles():
    rep = PerfReport(wall_start_ms=1000.0, wall_end_ms=2000.0)
    for i in range(10):
        s = PerfSample(session_id=f"s{i}", launch_ms=1000.0 + i * 10,
                       start_ms=1000.0 + i * 10 + 5, end_ms=1000.0 + i * 10 + 105,
                       ok=True, packets=5, sip=3)
        rep.samples.append(s)
    summ = rep.summary()
    assert summ["total"] == 10 and summ["success"] == 10 and summ["failed"] == 0
    assert summ["duration_ms"]["p50"] == pytest.approx(100, abs=1)
    assert summ["total_packets"] == 50
    assert summ["throughput_sps"] == pytest.approx(10.0, abs=0.1)  # 10 ok / 1s


def test_perf_report_failure_rate():
    rep = PerfReport(wall_start_ms=0, wall_end_ms=1000)
    rep.samples = [PerfSample("a", 0, ok=True), PerfSample("b", 0, ok=False, error="x")]
    assert rep.failure_rate == 0.5
    assert rep.summary()["failed"] == 1


def test_perf_flow_event_payload():
    rep = PerfReport(wall_start_ms=0, wall_end_ms=500)
    rep.samples = [PerfSample("a", 0, start_ms=0, end_ms=50, ok=True, packets=10)]
    ev = perf_flow_event(rep, scenario_id="T")
    assert ev.channel == "SYS" and ev.peer == "perf"
    assert ev.payload["total"] == 1 and ev.payload["total_packets"] == 10


# ── 부하 생성기 ──
async def test_loadgen_runs_n_sessions():
    ports = RtpPortAllocator(10001, 1000)
    runner = make_default_runner(feeder_factory=CollectingFeeder, port_alloc=ports,
                                 realtime=False)
    gen = LoadGenerator(runner)
    report = await gen.run(_scenario(), LoadSpec(total=8, cps=200.0, realtime=False))
    assert report.total == 8 and report.success == 8 and report.failed == 0
    # 각 세션 1 발언(0.1s=5frame) → packets 5
    assert report.total_packets() == 8 * 5
    assert report.throughput_sps() > 0


async def test_loadgen_records_failure():
    async def bad_runner(scenario, sid):
        raise RuntimeError("boom")

    gen = LoadGenerator(bad_runner)
    report = await gen.run(_scenario(), LoadSpec(total=3, cps=500.0))
    assert report.failed == 3 and report.success == 0
    assert all("boom" in s.error for s in report.samples)


# ── /api/perf 라우트 ──
def test_api_perf_run():
    state = AppState(feeder_factory=CollectingFeeder)
    client = TestClient(create_app(state))
    r = client.post("/api/perf/run",
                    json={"scenario_id": "MCPTT-GROUP-FLOOR", "total": 5, "cps": 200.0})
    assert r.status_code == 200
    summ = r.json()
    assert summ["total"] == 5 and summ["success"] == 5
    # 마지막 결과 조회
    assert client.get("/api/perf").json()["total"] == 5
    # perf 이벤트가 SYS 채널로 발행됨
    sys_perf = [e for e in client.get("/api/events", params={"channel": "SYS", "limit": 500}).json()
                if e["label"] == "perf result"]
    assert sys_perf
