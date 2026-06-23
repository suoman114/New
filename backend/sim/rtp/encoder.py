"""음원 → AMR-WB frame 생성.

ffmpeg/opencore-amr 미가용 환경에서는 **결정론적(deterministic) frame** 을 생성한다.
시뮬레이터는 어떤 frame 을 보냈는지 정확히 알아야 검증기가 골든 비교를 할 수 있으므로,
재현 가능한 합성 frame 이 오히려 유리하다. 실 음원 인코딩은 2차(opencore-amr)로 확장.
"""

from __future__ import annotations

import hashlib

from .amrwb import AMRWB_SPEECH_BITS, AmrFrame, NO_DATA_WB, SID_FT_WB, amrwb_frame_bytes


def _det_bytes(n: int, seed: int, idx: int) -> bytes:
    """seed/idx 로 재현 가능한 n바이트 생성."""
    out = bytearray()
    counter = 0
    while len(out) < n:
        h = hashlib.sha256(f"{seed}:{idx}:{counter}".encode()).digest()
        out += h
        counter += 1
    return bytes(out[:n])


def _zero_pad_tail(data: bytes, nbits: int) -> bytes:
    """speech bits(nbits) 이후 trailing padding bit 를 0 으로 (OA/BE 동치 보장)."""
    pad = len(data) * 8 - nbits
    if pad <= 0:
        return data
    buf = bytearray(data)
    buf[-1] &= (0xFF << pad) & 0xFF
    return bytes(buf)


def speech_frames(count: int, *, ft: int = 8, seed: int = 1) -> list[AmrFrame]:
    """지정 mode(ft)의 speech frame 을 count 개 생성(결정론적, padding bit=0)."""
    n = amrwb_frame_bytes(ft)
    return [AmrFrame(ft=ft, data=_zero_pad_tail(_det_bytes(n, seed, i), AMRWB_SPEECH_BITS[ft]))
            for i in range(count)]


def sid_frames(count: int = 1, *, seed: int = 2) -> list[AmrFrame]:
    """SID(comfort noise) frame."""
    n = amrwb_frame_bytes(SID_FT_WB)
    return [AmrFrame(ft=SID_FT_WB,
                     data=_zero_pad_tail(_det_bytes(n, seed, i), AMRWB_SPEECH_BITS[SID_FT_WB]))
            for i in range(count)]


def no_data_frames(count: int = 1) -> list[AmrFrame]:
    """NO_DATA frame (묵음/DTX 무음 구간)."""
    return [AmrFrame(ft=NO_DATA_WB, data=b"") for _ in range(count)]


def talk_spurt(duration_ms: int, *, ft: int = 8, seed: int = 1) -> list[AmrFrame]:
    """주어진 길이(ms)의 발언(talk spurt) frame 시퀀스 (20ms 단위)."""
    count = max(0, duration_ms // 20)
    return speech_frames(count, ft=ft, seed=seed)


# ── 실 음원 인코딩 확장 지점 (2차) ────────────────────────────────────────────
# 결정론적 합성 frame 대신 실제 WAV/PCM 을 AMR-WB 로 인코딩하려면 아래를 구현한다.
# opencore-amr(파이썬 바인딩) 또는 ffmpeg 서브프로세스를 연동한다(네이티브 의존).
def external_encoder_available() -> bool:
    """실 음원 AMR-WB 인코더(ffmpeg libvo_amrwbenc 등) 가용 여부."""
    from ..validator.decode_check import amrwb_encoder_available
    return amrwb_encoder_available()


# 부록6 AMR-WB mode-set → libvo_amrwbenc 비트레이트(bps)
_AMRWB_BITRATE = {0: 6600, 1: 8850, 2: 12650, 3: 14250, 4: 15850, 5: 18250,
                  6: 19850, 7: 23050, 8: 23850}


def _ffmpeg_encode_awb(source_audio: str, ft: int) -> list[AmrFrame]:
    """ffmpeg 로 WAV/PCM → AMR-WB(.awb) 인코딩 후 storage frame 파싱."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    from .amrwb import parse_storage

    fp = shutil.which("ffmpeg")
    src = Path(source_audio).expanduser()
    if not fp or not src.is_file():
        return []
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out.awb"
        try:
            subprocess.run(
                [fp, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                 "-ar", "16000", "-ac", "1", "-c:a", "libvo_amrwbenc",
                 "-b:a", str(_AMRWB_BITRATE.get(ft, 23850)), str(out)],
                capture_output=True, timeout=60, check=True)
            return parse_storage(out.read_bytes(), wb=True)
        except Exception:  # noqa: BLE001
            return []


def encode_source(source_audio: str | None, duration_ms: int, *, ft: int = 8,
                  seed: int = 1) -> list[AmrFrame]:
    """음원 → AMR-WB frame. 실 인코더 가용+음원 지정 시 ffmpeg 인코딩, 아니면 결정론적 합성.

    duration_ms 길이에 맞춰 frame 수를 자른다(부족 시 합성으로 채우지 않고 가용분만).
    """
    want = max(0, duration_ms // 20)
    if source_audio and external_encoder_available():
        frames = _ffmpeg_encode_awb(source_audio, ft)
        if frames:
            return frames[:want] if want else frames
    return talk_spurt(duration_ms, ft=ft, seed=seed)
