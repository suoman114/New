"""AMR-WB Bandwidth-Efficient(BE) 모드 패킷화/파싱 + OA 동치 검증."""

from sim.rtp import (
    AmrWbStream,
    encoder,
    packetize_be,
    packetize_oa,
    parse_be,
)
from sim.rtp.amrwb import AMRWB_SPEECH_BITS
from sim.scenario import ScenarioEngine, build_expectations
from sim.scenario.loader import Scenario
from sim.sip import amrwb_offer, build_sdp, parse_sdp
from sim.validator import Validator, reconstruct_awb


class _Collect:
    async def send_sip(self, data, *, event=None, session_id="", call_id="", label="SIP"):
        pass

    async def send_rtp(self, packet, port, *, session_id="", call_id=""):
        pass


def test_be_packetize_parse_roundtrip():
    frames = encoder.speech_frames(3, ft=8, seed=4)
    payload = packetize_be(frames)
    back = parse_be(payload)
    assert [f.ft for f in back] == [8, 8, 8]
    # padding bit=0 으로 정규화되어 byte 데이터까지 동일
    assert all(b.data == f.data for b, f in zip(back, frames))


def test_be_is_smaller_than_oa():
    frames = encoder.speech_frames(3, ft=8)
    be = packetize_be(frames)
    oa = packetize_oa(frames)
    # BE: ceil((4 + 6*3 + 477*3)/8) = 182, OA: 1 + 3 + 60*3 = 184
    assert len(be) < len(oa)
    assert len(be) == (4 + 6 * 3 + AMRWB_SPEECH_BITS[8] * 3 + 7) // 8


def test_be_multi_ft():
    frames = encoder.speech_frames(1, ft=0) + encoder.speech_frames(1, ft=8) + \
        encoder.sid_frames(1)
    back = parse_be(packetize_be(frames))
    assert [f.ft for f in back] == [0, 8, 9]
    assert all(b.data == f.data for b, f in zip(back, frames))


def test_sdp_be_offer_has_no_octet_align():
    sdp = parse_sdp(build_sdp(amrwb_offer("1.2.3.4", 30000, pt=98, octet_align=False)))
    assert sdp.audio().is_octet_aligned(98) is False
    assert sdp.audio().mode_set(98) == [8]


def test_stream_be_mode_payload_parses_as_be():
    frames = encoder.speech_frames(2, ft=8)
    pkts = AmrWbStream(ssrc=1, octet_align=False).build(frames)
    parsed = parse_be(pkts[0].payload)
    assert parsed[0].ft == 8 and parsed[0].data == frames[0].data


def _be_scenario(dur=0.2) -> Scenario:
    return Scenario.model_validate({
        "id": "T-BE", "service_type": "MCPTT",
        "media": {"mode_set": [8], "pt": 98, "octet_align": False, "duration_sec": dur},
        "mcptt": {"group_id": "98152020001", "members": [{"mdn": "tel:+82585102802"}]},
        "floor_sequence": [{"talker": "tel:+82585102802", "duration_sec": dur}],
    })


async def test_engine_be_end_to_end_and_validate(tmp_path):
    engine = ScenarioEngine(_Collect(), realtime=False)
    run = await engine.run(_be_scenario(0.2), session_id="be-1")
    sr = run.spurts[0]
    assert sr.octet_align is False and sr.sent_packets == 10
    # BE 페이로드가 정상 파싱되는지(파서 선택이 올바른지)
    assert parse_be(sr.packets[0].payload)[0].ft == 8

    # 검증기 골든(BE 경로)으로 서버파일 동일 → PASS
    v = Validator(fs_root=str(tmp_path), mode_set_max=8)
    golden = v.reconstruct_golden(sr)
    d = tmp_path / "MCPTT" / "VOICE"
    d.mkdir(parents=True)
    exp0 = run.expectations.talk_spurts[0]
    (d / f"M_{run.call_id}_{exp0.talker_digits}_{exp0.group_id}_20260620000000_5001.awb"
     ).write_bytes(golden)
    result = await v.validate(run.expectations, run.spurts)
    audio = [i for i in result.items if i.category == "AUDIO"]
    assert audio and all(i.status == "PASS" for i in audio)

    # BE 골든은 OA frame 재구성과 동일 storage(파일 포맷은 모드 무관) 여야 한다
    assert golden == reconstruct_awb(sr.frames, mode_set_max=8)


def test_build_expectations_be_scenario():
    exp = build_expectations(_be_scenario(0.1), session_id="s", call_id="c")
    assert len(exp.talk_spurts) == 1
