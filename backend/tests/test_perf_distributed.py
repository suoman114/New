"""대규모 분산 부하 + 이벤트 폭주 방지 테스트."""

from fastapi.testclient import TestClient

from api.main import create_app
from api.state import AppState
from sim.perf import DistributedLoadGenerator, NullFeeder
from sim.scenario.loader import Scenario


class CollectingFeeder:
    async def send_sip(self, data, *, event=None, session_id="", call_id="", label="SIP"):
        pass

    async def send_rtp(self, packet, port, *, session_id="", call_id=""):
        pass


def _small_scenario() -> Scenario:
    return Scenario.model_validate({
        "id": "T-DIST", "service_type": "MCPTT",
        "media": {"mode_set": [8], "pt": 98},
        "mcptt": {"group_id": "98152020001", "members": [{"mdn": "tel:+82585102802"}]},
        "floor_sequence": [{"talker": "tel:+82585102802", "duration_sec": 0.1}],
    })


async def test_null_feeder_noop():
    f = NullFeeder()
    await f.send_sip(b"x")
    await f.send_rtp(None, 10001)  # 무동작


async def test_distributed_load_multiprocess():
    gen = DistributedLoadGenerator()
    report = await gen.run(_small_scenario(), total=8, cps=200.0, workers=2)
    assert report.total == 8 and report.success == 8 and report.failed == 0
    # 각 세션 0.1s=5frame → 5 packet, 총 40
    assert report.total_packets() == 8 * 5
    summ = report.summary()
    assert summ["total"] == 8 and summ["failed"] == 0


async def test_distributed_workers_capped_to_total():
    gen = DistributedLoadGenerator()
    report = await gen.run(_small_scenario(), total=3, cps=500.0, workers=10)
    assert report.total == 3 and report.success == 3


def test_api_perf_distributed_route():
    state = AppState(feeder_factory=CollectingFeeder)
    client = TestClient(create_app(state))
    r = client.post("/api/perf/run", json={
        "scenario_id": "MCPTT-GROUP-FLOOR", "total": 6, "cps": 300.0, "workers": 2})
    assert r.status_code == 200
    assert r.json()["total"] == 6 and r.json()["success"] == 6


async def test_large_inprocess_load_suppresses_events():
    state = AppState(feeder_factory=CollectingFeeder)
    # 임계(50) 초과 → 엔진 이벤트 발행 억제(bus=None), perf 요약만 발행
    await state.run_load("MCPTT-GROUP-FLOOR", total=60, cps=1000.0)
    sys_events = state.bus.recent(channel="SYS", limit=10000)
    starts = [e for e in sys_events if "scenario start" in e.label]
    perf = [e for e in sys_events if e.label == "perf result"]
    assert starts == []              # 세션별 이벤트 폭주 없음
    assert len(perf) == 1            # 요약 1건만


async def test_small_inprocess_load_keeps_events():
    state = AppState(feeder_factory=CollectingFeeder)
    await state.run_load("MCPTT-GROUP-FLOOR", total=3, cps=1000.0)
    starts = [e for e in state.bus.recent(channel="SYS", limit=10000)
              if "scenario start" in e.label]
    assert len(starts) == 3          # 소규모는 이벤트 유지
