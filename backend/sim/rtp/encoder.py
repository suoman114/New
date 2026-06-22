"""음원 → AMR-WB frame 생성.

ffmpeg/opencore-amr 미가용 환경에서는 **결정론적(deterministic) frame** 을 생성한다.
시뮬레이터는 어떤 frame 을 보냈는지 정확히 알아야 검증기가 골든 비교를 할 수 있으므로,
재현 가능한 합성 frame 이 오히려 유리하다. 실 음원 인코딩은 2차(opencore-amr)로 확장.
"""

from __future__ import annotations

import hashlib

from .amrwb import AmrFrame, NO_DATA_WB, SID_FT_WB, amrwb_frame_bytes


def _det_bytes(n: int, seed: int, idx: int) -> bytes:
    """seed/idx 로 재현 가능한 n바이트 생성."""
    out = bytearray()
    counter = 0
    while len(out) < n:
        h = hashlib.sha256(f"{seed}:{idx}:{counter}".encode()).digest()
        out += h
        counter += 1
    return bytes(out[:n])


def speech_frames(count: int, *, ft: int = 8, seed: int = 1) -> list[AmrFrame]:
    """지정 mode(ft)의 speech frame 을 count 개 생성(결정론적)."""
    n = amrwb_frame_bytes(ft)
    return [AmrFrame(ft=ft, data=_det_bytes(n, seed, i)) for i in range(count)]


def sid_frames(count: int = 1, *, seed: int = 2) -> list[AmrFrame]:
    """SID(comfort noise) frame."""
    n = amrwb_frame_bytes(SID_FT_WB)
    return [AmrFrame(ft=SID_FT_WB, data=_det_bytes(n, seed, i)) for i in range(count)]


def no_data_frames(count: int = 1) -> list[AmrFrame]:
    """NO_DATA frame (묵음/DTX 무음 구간)."""
    return [AmrFrame(ft=NO_DATA_WB, data=b"") for _ in range(count)]


def talk_spurt(duration_ms: int, *, ft: int = 8, seed: int = 1) -> list[AmrFrame]:
    """주어진 길이(ms)의 발언(talk spurt) frame 시퀀스 (20ms 단위)."""
    count = max(0, duration_ms // 20)
    return speech_frames(count, ft=ft, seed=seed)
