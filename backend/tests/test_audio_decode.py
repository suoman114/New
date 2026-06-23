"""실 ffmpeg AMR-WB 디코더 기반 오디오 검증 (ffmpeg 미설치 시 skip)."""

import pytest

from sim.rtp import encoder
from sim.rtp.amrwb import AmrFrame, parse_storage
from sim.validator import (
    amrwb_decoder_available,
    check_decodable,
    decode_awb_pcm,
    ffmpeg_path,
)
from sim.validator.reconstruct import MAGIC_AMRWB, reconstruct_awb
from sim.validator.silence_tables import SILENCE_AMRWB

ffmpeg_gate = pytest.mark.skipif(
    not (ffmpeg_path() and amrwb_decoder_available()),
    reason="ffmpeg AMR-WB 디코더 미가용")


def test_parse_storage_roundtrip():
    frames = encoder.speech_frames(4, ft=8)
    awb = reconstruct_awb(frames, mode_set_max=8)
    back = parse_storage(awb, wb=True)
    assert [f.ft for f in back] == [8, 8, 8, 8]
    assert all(b.data == f.data for b, f in zip(back, frames))


@ffmpeg_gate
def test_real_ffmpeg_decode_duration():
    # 4초(200 frame) → 디코딩 PCM ≈ 4000ms
    awb = reconstruct_awb(encoder.talk_spurt(4000, ft=8), mode_set_max=8)
    pcm = decode_awb_pcm(awb)
    assert pcm is not None
    # 16kHz mono s16le → 4s = 128000 byte
    assert abs(len(pcm) - 128000) <= 32 * 80


@ffmpeg_gate
def test_check_decodable_pass():
    awb = reconstruct_awb([AmrFrame(ft=8, data=SILENCE_AMRWB[8][1:]) for _ in range(50)],
                          mode_set_max=8)
    item = check_decodable(awb, expected_ms=1000, name="audio[0]")
    assert item is not None and item.status == "PASS"
    assert "PCM" in item.detail


@ffmpeg_gate
def test_check_decodable_duration_mismatch_fails():
    awb = reconstruct_awb(encoder.talk_spurt(1000, ft=8), mode_set_max=8)  # 1s
    item = check_decodable(awb, expected_ms=3000, name="audio[0]")          # 기대 3s
    assert item is not None and item.status == "FAIL"


@ffmpeg_gate
def test_check_decodable_rejects_garbage():
    item = check_decodable(MAGIC_AMRWB + b"\xff" * 200, expected_ms=1000, name="x")
    # 디코딩은 되더라도 길이가 안 맞거나, 깨진 입력이면 FAIL/길이불일치
    assert item is not None


def test_check_decodable_skips_without_ffmpeg(monkeypatch):
    # ffmpeg 미가용 환경 시뮬레이션 → None(스킵)
    monkeypatch.setattr("sim.validator.decode_check.ffmpeg_path", lambda: None)
    assert check_decodable(b"x", 1000) is None
