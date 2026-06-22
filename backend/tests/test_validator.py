"""validator 테스트 — 묵음표, 골든 재구성, 오디오/파일/DB 검증, facade."""

from datetime import datetime
from pathlib import Path

from sim.platform.db import InMemoryRecordInfoRepository
from sim.platform.models import RecordInfo
from sim.rtp import encoder
from sim.rtp.amrwb import AMRWB_SPEECH_BITS, amrwb_frame_bytes
from sim.scenario import ScenarioEngine, build_expectations
from sim.scenario.loader import Scenario
from sim.validator import (
    MAGIC_AMRWB,
    SILENCE_AMRWB,
    Validator,
    check_db,
    check_files,
    compare_awb,
    reconstruct_awb,
)
from sim.validator.silence_tables import write_mute


# ── 묵음 패킷 표 ──────────────────────────────────────────────────────────────
def test_silence_table_lengths_match_appendix6():
    # 묵음 packet = header(1) + speech bytes(부록6)
    for ft in range(9):
        assert len(SILENCE_AMRWB[ft]) == 1 + (AMRWB_SPEECH_BITS[ft] + 7) // 8
    # 첫 byte = (FT<<3)|(Q=1<<2)
    assert SILENCE_AMRWB[8][0] == (8 << 3) | (1 << 2) == 0x44
    assert SILENCE_AMRWB[0][0] == 0x04


def test_write_mute_repeats():
    assert write_mute(3, mode=8) == SILENCE_AMRWB[8] * 3
    assert write_mute(0, mode=8) == b""


# ── 골든 재구성 ──────────────────────────────────────────────────────────────
def test_reconstruct_speech_only():
    frames = encoder.speech_frames(3, ft=8, seed=5)
    awb = reconstruct_awb(frames, mode_set_max=8)
    assert awb.startswith(MAGIC_AMRWB)
    # magic + 3 × (1 header + 60 speech)
    assert len(awb) == len(MAGIC_AMRWB) + 3 * (1 + amrwb_frame_bytes(8))
    # 첫 frame header = (8<<3)|(1<<2)
    assert awb[len(MAGIC_AMRWB)] == 0x44


def test_reconstruct_no_data_becomes_mute():
    frames = encoder.speech_frames(1, ft=8) + encoder.no_data_frames(1)
    awb = reconstruct_awb(frames, mode_set_max=8)
    body = awb[len(MAGIC_AMRWB):]
    # speech(61) + mute(61)
    assert body[:61] == reconstruct_awb(encoder.speech_frames(1, ft=8))[len(MAGIC_AMRWB):]
    assert body[61:] == SILENCE_AMRWB[8]


def test_reconstruct_sid_becomes_mute():
    frames = encoder.sid_frames(1)
    awb = reconstruct_awb(frames, mode_set_max=8)
    assert awb[len(MAGIC_AMRWB):] == SILENCE_AMRWB[8]


# ── 오디오 비교 ──────────────────────────────────────────────────────────────
def test_compare_awb_pass_and_fail():
    frames = encoder.speech_frames(4, ft=8)
    golden = reconstruct_awb(frames)
    assert compare_awb(golden, golden).status == "PASS"

    corrupted = bytearray(golden)
    corrupted[len(MAGIC_AMRWB) + 5] ^= 0xFF       # 한 frame 변조
    item = compare_awb(golden, bytes(corrupted))
    assert item.status == "FAIL" and "frame[0]" in item.detail

    short = golden[:-61]                            # frame 1개 누락
    item2 = compare_awb(golden, short)
    assert item2.status == "FAIL" and "frame 수" in item2.detail


# ── 파일 검증 ────────────────────────────────────────────────────────────────
def test_check_files_with_tmp(tmp_path: Path):
    sc = _mcptt_scenario()
    exp = build_expectations(sc, session_id="s", call_id="tb2bua-x_opf_ob2bua-abcd")
    # 발언0,1 파일 생성(매직 포함), 발언2는 빈 발언
    d = tmp_path / "MCPTT" / "VOICE" / "2026" / "06" / "20" / "00"
    d.mkdir(parents=True)
    for s in exp.talk_spurts:
        if s.expect_empty:
            continue
        fname = f"M_tb2bua-x_opf_ob2bua-abcd_{s.talker_digits}_{s.group_id}_20260620000000_{5000 + s.index}.awb"
        (d / fname).write_bytes(MAGIC_AMRWB + b"\x44" + b"\x00" * 60)

    items = check_files(exp, tmp_path)
    statuses = {i.name: i.status for i in items}
    assert all(v == "PASS" for v in statuses.values()), statuses


def test_check_files_missing_fails(tmp_path: Path):
    sc = _mcptt_scenario()
    exp = build_expectations(sc, session_id="s", call_id="c-1")
    items = check_files(exp, tmp_path)
    # 비어있지 않은 발언은 파일 없음 → FAIL, 빈 발언은 PASS
    non_empty = [i for i, s in zip(items, exp.talk_spurts) if not s.expect_empty]
    assert all(i.status == "FAIL" for i in non_empty)


# ── DB 검증 ──────────────────────────────────────────────────────────────────
def test_check_db_pass():
    sc = _mcptt_scenario()
    call_id = "tb2bua-grp_opf_ob2bua-zzzz"
    exp = build_expectations(sc, session_id="s", call_id=call_id)
    repo = InMemoryRecordInfoRepository()
    for i, s in enumerate(t for t in exp.talk_spurts if not t.expect_empty):
        repo.add(RecordInfo(
            sip_callid=call_id, file_index=5000 + i, record_type="AUDIO",
            audio_extension="awb", file_status=2, mcptt_group_id=s.group_id,
            caller_file_name=f"M_{call_id}_{s.talker_digits}_{s.group_id}_20260620000000",
            create_time=datetime.now()))
    items = check_db(exp, repo)
    assert all(i.status == "PASS" for i in items), [i for i in items if i.status != "PASS"]


def test_check_db_detects_incomplete_status():
    sc = _mcptt_scenario()
    call_id = "c-db2"
    exp = build_expectations(sc, session_id="s", call_id=call_id)
    repo = InMemoryRecordInfoRepository()
    s0 = exp.talk_spurts[0]
    repo.add(RecordInfo(sip_callid=call_id, file_index=1, audio_extension="awb",
                        file_status=0,  # 저장중(미완료)
                        mcptt_group_id=s0.group_id,
                        caller_file_name=f"M_x_{s0.talker_digits}_{s0.group_id}_t"))
    items = check_db(exp, repo)
    statuses = [i for i in items if i.name.endswith("FILE_STATUS")]
    assert any(i.status == "FAIL" for i in statuses)


# ── facade: 엔진 송출 → 검증 통합 ───────────────────────────────────────────
async def test_validator_facade_audio_pass(tmp_path: Path):
    sc = _mcptt_scenario(durations=[0.2, 0.0])  # 발언0=10frame, 발언1=빈발언
    feeder = _Collect()
    engine = ScenarioEngine(feeder, realtime=False)
    run = await engine.run(sc, session_id="sx")

    # 서버 파일을 골든과 동일하게 생성(=정상 녹취 가정)
    d = tmp_path / "MCPTT" / "VOICE"
    d.mkdir(parents=True)
    s0 = run.spurts[0]
    golden = reconstruct_awb(s0.frames, mode_set_max=8)
    digits = run.expectations.talk_spurts[0].talker_digits
    gid = run.expectations.talk_spurts[0].group_id
    (d / f"M_{run.call_id}_{digits}_{gid}_20260620000000_5001.awb").write_bytes(golden)

    v = Validator(fs_root=str(tmp_path), mode_set_max=8)
    result = await v.validate(run.expectations, run.spurts)
    audio_items = [i for i in result.items if i.category == "AUDIO"]
    assert audio_items and all(i.status == "PASS" for i in audio_items)


async def test_validator_facade_audio_fail_on_corruption(tmp_path: Path):
    sc = _mcptt_scenario(durations=[0.2])
    feeder = _Collect()
    engine = ScenarioEngine(feeder, realtime=False)
    run = await engine.run(sc, session_id="sy")

    d = tmp_path / "MCPTT" / "VOICE"
    d.mkdir(parents=True)
    s0 = run.spurts[0]
    golden = bytearray(reconstruct_awb(s0.frames, mode_set_max=8))
    golden[len(MAGIC_AMRWB) + 3] ^= 0xFF
    digits = run.expectations.talk_spurts[0].talker_digits
    gid = run.expectations.talk_spurts[0].group_id
    (d / f"M_{run.call_id}_{digits}_{gid}_20260620000000_5001.awb").write_bytes(bytes(golden))

    v = Validator(fs_root=str(tmp_path), mode_set_max=8)
    result = await v.validate(run.expectations, run.spurts)
    assert result.passed is False


# ── helpers ──────────────────────────────────────────────────────────────────
class _Collect:
    async def send_sip(self, data, *, event=None, session_id="", call_id="", label="SIP"):
        pass

    async def send_rtp(self, packet, port, *, session_id="", call_id=""):
        pass


def _mcptt_scenario(durations=None) -> Scenario:
    durations = durations if durations is not None else [4, 6, 0]
    return Scenario.model_validate({
        "id": "T-MCPTT",
        "service_type": "MCPTT",
        "media": {"codec": "AMR-WB", "mode_set": [8], "pt": 98},
        "mcptt": {"group_id": "98152020001",
                  "members": [{"mdn": "tel:+82585102802"}, {"mdn": "tel:+82585109004"},
                              {"mdn": "tel:+82585102903"}]},
        "floor_sequence": [
            {"talker": ["tel:+82585102802", "tel:+82585109004", "tel:+82585102903"][i % 3],
             "duration_sec": d}
            for i, d in enumerate(durations)
        ],
    })
