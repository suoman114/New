"""rmq-monitor 테스트 — 실 로그 메시지 디코드/검증, floor 시퀀스, 모니터 graceful degrade."""


from sim.platform.config import RmqConfig
from sim.platform.eventbus import EventBus
from sim.rmq import CallRmqTracker, RmqMonitor, decode, validate_header
from sim.scenario.expectations import ScenarioExpectations

# 실 로그에서 발췌
HEARTBEAT = {
    "header": {"type": "heartbeat_indi", "callId": "uuid-hb", "transactionId": "t-hb",
               "msgFrom": "VCMM_0", "trxType": 0, "reasonCode": 2000, "reason": "Success"},
    "body": {"vcmmId": 0, "session_total": 16000, "session_idle": 15972},
}
CHANGE_TAKEN = {
    "header": {"type": "recording_change_req", "callId": "call-1", "transactionId": "t-1",
               "msgFrom": "VCMM_0", "trxType": 0, "reasonCode": 2000, "reason": "Success"},
    "body": {"type": "TAKEN", "caller_mdn": "tel:+82585102802", "audio_extension": "awb"},
}
CHANGE_RES = {
    "header": {"type": "recording_change_res", "callId": "call-1", "transactionId": "t-1",
               "msgFrom": "VCMC", "trxType": 0, "reasonCode": 0},
    "body": {"type": "TAKEN", "file_index": 5008, "save_file_name": "M_call-1_585102802_..."},
}
CHANGE_IDLE = {
    "header": {"type": "recording_change_req", "callId": "call-1", "transactionId": "t-2",
               "msgFrom": "VCMM_0", "trxType": 0, "reasonCode": 2000, "reason": "Success"},
    "body": {"type": "IDLE"},
}
START_ERR = {
    "header": {"type": "recording_start_res", "callId": "call-1", "transactionId": "t-9",
               "msgFrom": "VCMM_0", "trxType": 1, "reasonCode": 3001,
               "reason": "Callee SDP is null"},
    "body": {},
}


def test_decode_heartbeat():
    msg = decode(HEARTBEAT)
    assert msg.type == "heartbeat_indi"
    assert msg.is_success and msg.body["session_total"] == 16000
    assert msg.header.transaction_id == "t-hb"


def test_decode_floor_change():
    msg = decode(CHANGE_TAKEN)
    assert msg.floor_type == "TAKEN"
    assert msg.body["caller_mdn"] == "tel:+82585102802"


def test_decode_error_message():
    msg = decode(START_ERR)
    assert msg.is_error and msg.header.reason == "Callee SDP is null"


def test_validate_header_pass_and_fail():
    ok = validate_header(decode(CHANGE_TAKEN))
    assert all(i.status == "PASS" for i in ok)
    bad = decode({"header": {"type": "recording_stop_req"}, "body": {}})
    issues = validate_header(bad)
    assert any(i.status == "FAIL" for i in issues)


def test_tracker_floor_sequence_and_pairing():
    tr = CallRmqTracker("call-1")
    for m in (CHANGE_TAKEN, CHANGE_RES, CHANGE_IDLE):
        tr.add(decode(m))
    assert tr.change_sequence == ["TAKEN", "IDLE"]

    exp = ScenarioExpectations(session_id="s", call_id="call-1", service_type="MCPTT",
                               rmq_change_sequence=["TAKEN", "IDLE"])
    items = tr.validate(exp)
    seq = next(i for i in items if i.name == "floor_sequence")
    assert seq.status == "PASS"
    # t-2(IDLE)는 res 가 없음 → 미응답 1 → txn_pairing FAIL
    pairing = next(i for i in items if i.name == "txn_pairing")
    assert pairing.status == "FAIL"


def test_tracker_detects_error_code():
    tr = CallRmqTracker("call-1")
    tr.add(decode(START_ERR))
    err = next(i for i in tr.validate().__iter__() if i.name == "error_codes")
    assert err.status == "FAIL" and "Callee SDP is null" in err.detail


def test_tracker_sequence_mismatch_fails():
    tr = CallRmqTracker("call-1")
    tr.add(decode(CHANGE_TAKEN))  # TAKEN 만
    exp = ScenarioExpectations(session_id="s", call_id="call-1", service_type="MCPTT",
                               rmq_change_sequence=["TAKEN", "IDLE"])
    seq = next(i for i in tr.validate(exp) if i.name == "floor_sequence")
    assert seq.status == "FAIL"


async def test_monitor_handle_publishes_and_tracks():
    bus = EventBus()
    mon = RmqMonitor(RmqConfig(enabled=True), bus=bus, session_id="s1")
    for m in (HEARTBEAT, CHANGE_TAKEN, CHANGE_RES, CHANGE_IDLE):
        await mon.handle(m)
    # ladder 이벤트 발행
    rmq_events = bus.recent(channel="RMQ", limit=100)
    assert len(rmq_events) == 4
    taken = [e for e in rmq_events if "TAKEN" in e.label]
    assert taken and taken[0].peer == "VCMM_0"
    # call-1 트래커에 3건 누적(heartbeat 는 callId=uuid-hb 로 별도)
    assert mon.tracker_for("call-1").change_sequence == ["TAKEN", "IDLE"]


async def test_monitor_graceful_degrade_when_disabled():
    mon = RmqMonitor(RmqConfig(enabled=False))
    ok = await mon.start()
    assert ok is False and mon.enabled is False


async def test_monitor_graceful_degrade_on_connect_failure():
    # 닿을 수 없는 포트 → 연결 실패해도 예외 없이 False
    cfg = RmqConfig(enabled=True, host="127.0.0.1", port=1)
    mon = RmqMonitor(cfg)
    ok = await mon.start()
    assert ok is False and mon.enabled is False
