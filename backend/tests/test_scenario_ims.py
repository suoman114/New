"""IMS 시나리오 테스트 — 양레그 기대값, 엔진 엔드투엔드, 검증."""

import re
from pathlib import Path

from sim.platform.config import find_config_path
from sim.scenario import ScenarioEngine, build_expectations, load_scenario
from sim.scenario.expectations import mdn_local
from sim.scenario.loader import Scenario
from sim.validator import Validator, reconstruct_awb


class CollectingFeeder:
    def __init__(self):
        self.sip = []
        self.rtp = []

    async def send_sip(self, data, *, event=None, session_id="", call_id="", label="SIP"):
        self.sip.append(data)

    async def send_rtp(self, packet, port, *, session_id="", call_id=""):
        self.rtp.append((port, packet))


def _ims_scenario(duration=0.2) -> Scenario:
    return Scenario.model_validate({
        "id": "T-IMS", "service_type": "IMS",
        "media": {"codec": "AMR-WB", "mode_set": [8], "pt": 98, "duration_sec": duration},
        "call": {"outbound": 0, "from_no": "01011113333", "to_no": "01012341234"},
    })


def test_mdn_local_country_code():
    assert mdn_local("+821358512668") == "01358512668"
    assert mdn_local("01012341234") == "01012341234"


def test_ims_expectations_two_legs():
    exp = build_expectations(_ims_scenario(), session_id="s", call_id="1339_808@1.2.3.4")
    assert exp.service_type == "IMS"
    assert len(exp.talk_spurts) == 2
    assert exp.db_min_rows == 1
    assert exp.rmq_change_sequence == []
    caller, callee = exp.talk_spurts
    assert caller.file_prefix == "I" and caller.audio_ext == "awb"
    # caller: I_..._{from}_{to}_ts , callee: 역순
    real_caller = "I_1339172425_809000108@104.240.17.77_01011113333_01012341234_20260620015023.awb"
    real_callee = "I_1339172425_809000108@104.240.17.77_01012341234_01011113333_20260620015023.awb"
    assert re.match(caller.name_regex, real_caller)
    assert re.match(callee.name_regex, real_callee)
    assert not re.match(caller.name_regex, real_callee)


def test_ims_loader_scenario_exists():
    sc = load_scenario(find_config_path().parent / "scenarios" / "IMS-VOICE-INBOUND.yaml")
    assert sc.service_type == "IMS" and sc.call is not None
    assert sc.call.from_no and sc.call.to_no


async def test_ims_engine_end_to_end():
    feeder = CollectingFeeder()
    engine = ScenarioEngine(feeder, realtime=False)
    run = await engine.run(_ims_scenario(0.2), session_id="ims-1")

    assert run.service_type == "IMS"
    assert len(run.spurts) == 2                       # caller/callee 레그
    assert run.sip_count == 3                         # INVITE/ACK/BYE
    # 각 레그 10 frame(0.2s) → 10 packet, 총 20
    assert all(s.sent_packets == 10 for s in run.spurts)
    assert len(feeder.rtp) == 20
    assert run.call_id.endswith("@104.240.17.77")


async def test_ims_no_floor_but_start_stop_events():
    from sim.platform.eventbus import EventBus

    bus = EventBus()
    engine = ScenarioEngine(CollectingFeeder(), bus=bus, realtime=False)
    await engine.run(_ims_scenario(0.1), session_id="ims-2")
    rmq = bus.recent(channel="RMQ", limit=100)
    labels = [e.label for e in rmq]
    assert "recording_start_req" in labels and "recording_stop_req" in labels
    assert "floor TAKEN" not in labels                # IMS 는 floor 없음


async def test_ims_validator_audio_pass(tmp_path: Path):
    engine = ScenarioEngine(CollectingFeeder(), realtime=False)
    run = await engine.run(_ims_scenario(0.2), session_id="ims-3")

    d = tmp_path / "IMS" / "VOICE"
    d.mkdir(parents=True)
    # 양 레그 골든 파일 생성(정상 녹취 가정)
    for sr, exp in zip(run.spurts, run.expectations.talk_spurts):
        golden = reconstruct_awb(sr.frames, mode_set_max=8)
        a, b = (exp.talker_digits,
                ("01012341234" if exp.index == 0 else "01011113333"))
        (d / f"I_{run.call_id}_{a}_{b}_20260620000000.awb").write_bytes(golden)

    v = Validator(fs_root=str(tmp_path), mode_set_max=8)
    result = await v.validate(run.expectations, run.spurts)
    audio = [i for i in result.items if i.category == "AUDIO"]
    # 레그별 byte 비교 2건(+ ffmpeg 가용 시 decode 검증). 전부 PASS.
    compares = [i for i in audio if i.name in ("audio[0]", "audio[1]")]
    assert len(compares) == 2 and all(i.status == "PASS" for i in audio)
