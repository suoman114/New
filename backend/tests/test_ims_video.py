"""IMS H.264 영상 시나리오 — 송출 엔진 + 골든 검증 E2E."""

from pathlib import Path

from sim.platform.config import find_config_path
from sim.rtp import H264Stream
from sim.rtp.h264 import depacketize, synthetic_nals, to_annexb
from sim.scenario import ScenarioEngine, build_expectations, load_scenario
from sim.scenario.loader import Scenario
from sim.validator import Validator, reconstruct_annexb


class _Collect:
    def __init__(self):
        self.rtp = []

    async def send_sip(self, data, *, event=None, session_id="", call_id="", label="SIP"):
        pass

    async def send_rtp(self, packet, port, *, session_id="", call_id=""):
        self.rtp.append((port, packet))


def _video_scenario(dur=0.2) -> Scenario:
    return Scenario.model_validate({
        "id": "T-VIDEO", "service_type": "IMS",
        "media": {"codec": "H264", "clock": 90000, "pt": 96, "duration_sec": dur,
                  "packetization_mode": 1},
        "call": {"outbound": 0, "from_no": "01011113333", "to_no": "01012341234"},
    })


def test_h264_stream_payloads_reconstruct():
    nals = synthetic_nals(6, size=300)            # 큰 NAL → FU-A 분할 유발
    _, payloads = H264Stream(ssrc=1, mtu=100).build(nals)
    # 송출 payload 를 de-packetize 하면 원본 NAL 복원
    assert depacketize(payloads) == nals
    assert reconstruct_annexb(payloads) == to_annexb(nals)


def test_video_expectations():
    exp = build_expectations(_video_scenario(), session_id="s", call_id="1_2@ip")
    assert len(exp.talk_spurts) == 1
    ts = exp.talk_spurts[0]
    assert ts.media_kind == "video" and ts.audio_ext == "h264"
    import re
    assert re.match(ts.name_regex,
                    "I_1_2@ip_01011113333_01012341234_20260620000000.h264")


def test_ims_video_loader():
    sc = load_scenario(find_config_path().parent / "scenarios" / "IMS-VIDEO.yaml")
    assert sc.service_type == "IMS" and sc.media.codec == "H264"


async def test_engine_video_end_to_end():
    feeder = _Collect()
    run = await ScenarioEngine(feeder, realtime=False).run(_video_scenario(0.2),
                                                           session_id="v1")
    assert run.service_type == "IMS"
    sr = run.spurts[0]
    assert sr.media_kind == "video" and sr.video_payloads
    assert sr.sent_packets == len(feeder.rtp)
    # payload 로 Annex B 재구성 가능
    assert reconstruct_annexb(sr.video_payloads).startswith(b"\x00\x00\x00\x01")


async def test_video_validator_pass_and_fail(tmp_path: Path):
    feeder = _Collect()
    run = await ScenarioEngine(feeder, realtime=False).run(_video_scenario(0.2),
                                                           session_id="v2")
    v = Validator(fs_root=str(tmp_path), mode_set_max=8)
    golden = v.reconstruct_golden(run.spurts[0])
    assert golden.startswith(b"\x00\x00\x00\x01")

    d = tmp_path / "IMS" / "VIDEO"
    d.mkdir(parents=True)
    fname = f"I_{run.call_id}_01011113333_01012341234_20260620000000.h264"
    (d / fname).write_bytes(golden)

    res = await v.validate(run.expectations, run.spurts)
    video = [i for i in res.items if i.name.startswith("video[")]
    assert video and all(i.status == "PASS" for i in video)

    # 변조 → FAIL
    bad = bytearray(golden)
    bad[-1] ^= 0xFF
    (d / fname).write_bytes(bytes(bad))
    res2 = await v.validate(run.expectations, run.spurts)
    assert res2.passed is False
