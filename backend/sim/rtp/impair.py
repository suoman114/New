"""현실/네거티브 시뮬레이션: 패킷 손실, 지터, 묵음(DTX) 삽입.

검증기는 timestamp 증가분으로 손실/묵음을 재구성하므로(부록5), 손실은 **seq/ts 는 유지**한 채
패킷만 드롭한다(수신측에 gap 으로 보임).
"""

from __future__ import annotations

import random

from .amrwb import AmrFrame
from .encoder import no_data_frames
from .rtp import RtpPacket


def drop_by_indices(packets: list[RtpPacket], indices: set[int]) -> list[RtpPacket]:
    """지정 인덱스의 패킷을 드롭(seq gap 발생)."""
    return [p for i, p in enumerate(packets) if i not in indices]


def drop_random(packets: list[RtpPacket], loss_pct: float,
                seed: int = 0) -> tuple[list[RtpPacket], set[int]]:
    """확률적 손실. 드롭된 인덱스 집합도 함께 반환."""
    if loss_pct <= 0:
        return list(packets), set()
    rng = random.Random(seed)
    dropped = {i for i in range(len(packets)) if rng.random() * 100.0 < loss_pct}
    return drop_by_indices(packets, dropped), dropped


def jitter_schedule(count: int, base_interval_ms: int = 20, jitter_ms: int = 0,
                    seed: int = 0) -> list[float]:
    """각 패킷의 송출 시각(ms, 누적) 스케줄. jitter_ms 범위에서 흔든다."""
    rng = random.Random(seed)
    schedule: list[float] = []
    t = 0.0
    for _ in range(count):
        schedule.append(t)
        delta = base_interval_ms
        if jitter_ms:
            delta += rng.uniform(-jitter_ms, jitter_ms)
        t += max(0.0, delta)
    return schedule


def inject_silence(frames: list[AmrFrame], every: int, run: int = 1) -> list[AmrFrame]:
    """`every` frame 마다 `run` 개의 NO_DATA(묵음) frame 을 삽입."""
    if every <= 0:
        return list(frames)
    out: list[AmrFrame] = []
    for i, fr in enumerate(frames):
        out.append(fr)
        if (i + 1) % every == 0:
            out.extend(no_data_frames(run))
    return out
