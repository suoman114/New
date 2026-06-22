"""platform.models 계약 테스트 — FlowEvent / ValidationResult / RecordInfo."""

from sim.platform.models import (
    FlowEvent,
    RecordInfo,
    ValidationItem,
    ValidationResult,
)


def test_flowevent_defaults_and_logref():
    ev = FlowEvent(session_id="s1", call_id="c1", channel="SIP", label="INVITE")
    assert ev.event_id  # 자동 생성
    assert ev.ts > 0
    # log_ref 미지정 시 event_id 와 동일
    assert ev.log_ref == ev.event_id
    assert ev.severity == "info"
    assert ev.direction == "SIM-INTERNAL"


def test_flowevent_json_roundtrip():
    ev = FlowEvent(
        session_id="s1",
        call_id="1339172425_809000108@104.240.17.77",
        channel="RMQ",
        direction="SUT-INTERNAL",
        peer="VCMM_0",
        label="recording_change_req",
        payload={"type": "TAKEN", "caller_mdn": "tel:+82585102802"},
    )
    js = ev.model_dump_json()
    back = FlowEvent.model_validate_json(js)
    assert back.event_id == ev.event_id
    assert back.payload["type"] == "TAKEN"
    assert back.peer == "VCMM_0"


def test_validation_result_pass_fail():
    res = ValidationResult(session_id="s1", call_id="c1")
    res.add(ValidationItem(category="FILE", name="exists", status="PASS"))
    assert res.passed is True
    res.add(ValidationItem(category="DB", name="file_status", status="FAIL",
                           expected=2, actual=0, detail="저장 미완료"))
    assert res.passed is False
    assert len(res.items) == 2


def test_recordinfo_fields_match_asbuilt():
    rec = RecordInfo(
        sip_callid="tb2bua-...-0ad2",
        file_index=5008,
        record_type="AUDIO",
        audio_extension="awb",
        file_status=2,
        reason_cord=2,
        reason_str="SUCCESS",
        mcptt_group_id="98152020001",
        caller_file_name="M_..._585102802_98152020001_20260620000036",
    )
    assert rec.file_index == 5008
    assert rec.file_status == 2
    assert rec.mcptt_group_id == "98152020001"
