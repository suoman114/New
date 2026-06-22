"""실 서버 통합 경로 테스트 (오프라인: 인메모리 repo + tmp 파일 + RMQ handle 주입)."""


from fastapi.testclient import TestClient

from api.main import create_app
from api.state import AppState
from sim.platform.config import load_config
from sim.platform.db import InMemoryRecordInfoRepository
from sim.platform.models import RecordInfo


class CollectingFeeder:
    async def send_sip(self, data, *, event=None, session_id="", call_id="", label="SIP"):
        pass

    async def send_rtp(self, packet, port, *, session_id="", call_id=""):
        pass


def test_env_override(monkeypatch):
    monkeypatch.setenv("UVCS_DB_HOST", "10.1.2.3")
    monkeypatch.setenv("UVCS_DB_PASSWORD", "secret")
    monkeypatch.setenv("UVCS_RMQ_ENABLED", "false")
    monkeypatch.setenv("UVCS_REC_RAMDISK", "/tmp/ramdisk-x")
    cfg = load_config()
    assert cfg.sut.db.host == "10.1.2.3"
    assert cfg.sut.db.password == "secret"
    assert cfg.rmq.enabled is False
    assert cfg.sut.rec_ramdisk == "/tmp/ramdisk-x"


def test_integration_health_no_backends():
    cfg = load_config()
    cfg.rmq.enabled = False
    cfg.sut.rec_ramdisk = "/nonexistent/ramdisk"
    cfg.sut.rec_nas = "/nonexistent/nas"
    # repo_factory 가 연결 실패를 던지면 db.reachable=False 로 graceful degrade
    state = AppState(config=cfg, feeder_factory=CollectingFeeder,
                     repo_factory=lambda db: (_ for _ in ()).throw(RuntimeError("no db")))
    health = state.integration_health()
    assert health["db"]["reachable"] is False
    assert health["rmq"]["enabled"] is False
    assert health["fs"]["active_root"] is None
    assert health["inject_mode"] == "tapper_udp"


def test_validate_session_with_db_and_files(tmp_path, monkeypatch):
    # 램디스크를 tmp 로 가리키고, 인메모리 DB repo 주입
    cfg = load_config()
    cfg.rmq.enabled = False
    cfg.sut.rec_ramdisk = str(tmp_path)

    rows: list[RecordInfo] = []
    repo = InMemoryRecordInfoRepository(rows)
    state = AppState(config=cfg, feeder_factory=CollectingFeeder, repo_factory=lambda db: repo)
    client = TestClient(create_app(state))

    # 1) 시나리오 실행(대기)
    sid = client.post("/api/run", json={"scenario_id": "MCPTT-GROUP-FLOOR", "wait": True}
                      ).json()["session_ids"][0]
    run = state.run_results[sid]

    # 2) 서버 산출물 시뮬레이트: 골든 파일 + TBL_RECORD_INFO 행 생성
    from sim.validator import Validator
    v = Validator(mode_set_max=8)
    d = tmp_path / "MCPTT" / "VOICE"
    d.mkdir(parents=True)
    for sr, exp in zip(run.spurts, run.expectations.talk_spurts):
        if exp.expect_empty:
            continue
        golden = v.reconstruct_golden(sr)
        fname = f"M_{run.call_id}_{exp.talker_digits}_{exp.group_id}_20260620000000_{5000 + sr.index}.awb"
        (d / fname).write_bytes(golden)
        repo.add(RecordInfo(
            sip_callid=run.call_id, file_index=5000 + sr.index, record_type="AUDIO",
            audio_extension="awb", file_status=2, mcptt_group_id=exp.group_id,
            caller_file_name=fname[:-4]))

    # 3) 검증 실행
    res = client.post(f"/api/validate?session_id={sid}").json()
    cats = {i["category"] for i in res["items"]}
    assert "FILE" in cats and "DB" in cats and "AUDIO" in cats
    fails = [i for i in res["items"] if i["status"] == "FAIL"]
    assert not fails, fails

    # 세션 검증 통과 플래그
    me = next(s for s in client.get("/api/sessions").json() if s["session_id"] == sid)
    assert me["validation_passed"] is True


def test_health_endpoint_served():
    state = AppState(config=load_config(), feeder_factory=CollectingFeeder,
                     repo_factory=lambda db: InMemoryRecordInfoRepository())
    client = TestClient(create_app(state))
    h = client.get("/api/integration/health").json()
    assert "db" in h and "rmq" in h and "fs" in h
    # 인메모리 repo 는 healthcheck 조회 성공 → reachable True
    assert h["db"]["reachable"] is True
