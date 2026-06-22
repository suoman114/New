"""부록5 완전판 — timestamp-gap 묵음 채움 재구성 검증."""

from pathlib import Path

from sim.rtp import encoder
from sim.rtp.impair import drop_by_indices
from sim.rtp.sender import AmrWbStream
from sim.scenario import ScenarioEngine, load_scenario
from sim.scenario.loader import Scenario
from sim.validator import Validator, reconstruct_awb
from sim.validator.reconstruct import (
    MAGIC_AMRWB,
    frame_count_of,
    reconstruct_from_packets,
)
from sim.validator.silence_tables import SILENCE_AMRWB
from sim.platform.config import find_config_path


class _Collect:
    async def send_sip(self, data, *, event=None, session_id="", call_id="", label="SIP"):
        pass

    async def send_rtp(self, packet, port, *, session_id="", call_id=""):
        pass


REC = 1 + 60  # FT8 storage record = header + 60 speech bytes


def test_gap_fill_inserts_mute_for_lost_packet():
    frames = encoder.speech_frames(5, ft=8, seed=3)
    packets = AmrWbStream(ssrc=1, start_seq=0, start_ts=0).build(frames)  # ts 0..1280
    kept = drop_by_indices(packets, {2})                                  # ts=640 손실

    golden = reconstruct_from_packets(kept, mode_set_max=8)
    # magic + rec0 + rec1 + mute(채움) + rec3 + rec4 = 5 record
    assert len(golden) == len(MAGIC_AMRWB) + 5 * REC
    body = golden[len(MAGIC_AMRWB):]
    # 3번째(index2) record 가 손실 채움 묵음
    assert body[2 * REC:3 * REC] == SILENCE_AMRWB[8]
    assert frame_count_of(golden) == 5


def test_gap_fill_differs_from_naive_reconstruct():
    frames = encoder.speech_frames(6, ft=8)
    packets = AmrWbStream(ssrc=1, start_seq=0, start_ts=0).build(frames)
    kept = drop_by_indices(packets, {2, 3})  # 내부 2개 손실
    kept_frames = encoder.speech_frames(6, ft=8)
    kept_frames = [kept_frames[i] for i in (0, 1, 4, 5)]

    gap = reconstruct_from_packets(kept, mode_set_max=8)
    naive = reconstruct_awb(kept_frames, mode_set_max=8)
    # gap-fill 은 손실 구간을 묵음으로 메워 원래 길이(6 record)를 복원
    assert frame_count_of(gap) == 6
    assert frame_count_of(naive) == 4
    assert len(gap) > len(naive)


def test_no_loss_gap_fill_equals_naive():
    frames = encoder.speech_frames(5, ft=8, seed=9)
    packets = AmrWbStream(ssrc=2, start_seq=0, start_ts=0).build(frames)
    assert reconstruct_from_packets(packets, mode_set_max=8) == \
        reconstruct_awb(frames, mode_set_max=8)


def test_packet_loss_scenario_loads():
    sc = load_scenario(find_config_path().parent / "scenarios" / "PACKET-LOSS.yaml")
    assert sc.impair.packet_loss_pct == 20


async def test_validator_uses_packet_golden_under_loss(tmp_path: Path):
    sc = Scenario.model_validate({
        "id": "T-LOSS", "service_type": "MCPTT",
        "media": {"mode_set": [8], "pt": 98},
        "mcptt": {"group_id": "98152020001", "members": [{"mdn": "tel:+82585102802"}]},
        "floor_sequence": [{"talker": "tel:+82585102802", "duration_sec": 1}],
        "impair": {"packet_loss_pct": 30},
    })
    engine = ScenarioEngine(_Collect(), realtime=False)
    run = await engine.run(sc, session_id="loss-1")
    sr = run.spurts[0]
    assert sr.dropped > 0 and sr.packets  # 손실 발생 + 패킷 보존

    # 서버 파일 = 검증기와 동일한 packet 기반 골든(=정상 녹취 가정)
    v = Validator(fs_root=str(tmp_path), mode_set_max=8)
    golden = v.reconstruct_golden(sr)
    # gap-fill 로 손실분이 묵음으로 메워져 송신 패킷수보다 record 가 많다
    assert frame_count_of(golden) >= sr.sent_packets

    d = tmp_path / "MCPTT" / "VOICE"
    d.mkdir(parents=True)
    exp0 = run.expectations.talk_spurts[0]
    (d / f"M_{run.call_id}_{exp0.talker_digits}_{exp0.group_id}_20260620000000_5001.awb"
     ).write_bytes(golden)

    result = await v.validate(run.expectations, run.spurts)
    audio = [i for i in result.items if i.category == "AUDIO"]
    assert audio and all(i.status == "PASS" for i in audio)
