"""실 ffmpeg AMR-WB 디코더 기반 오디오 검증 (선택적, ffmpeg 가용 시).

골든 byte 비교(audio_check)에 더해, 서버 저장 `.awb` 가 **실제로 유효한 AMR-WB** 이며
기대 재생시간으로 디코딩되는지 실 디코더로 확인한다(구조 무결성 + 길이).
ffmpeg 미설치 시 모든 함수는 graceful 하게 동작(검증 스킵).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ..platform.models import ValidationItem

# 16kHz mono s16le → 1ms = 16 sample × 2 byte = 32 byte
_BYTES_PER_MS = 32


def ffmpeg_path() -> Optional[str]:
    return shutil.which("ffmpeg")


def _codecs(kind: str) -> str:
    fp = ffmpeg_path()
    if not fp:
        return ""
    try:
        out = subprocess.run([fp, "-hide_banner", f"-{kind}"], capture_output=True,
                             text=True, timeout=10)
        return out.stdout
    except Exception:  # noqa: BLE001
        return ""


def amrwb_decoder_available() -> bool:
    return "amrwb" in _codecs("decoders") or "amr_wb" in _codecs("decoders")


def amrwb_encoder_available() -> bool:
    return "amr_wb" in _codecs("encoders") or "libvo_amrwbenc" in _codecs("encoders")


def decode_awb_pcm(awb_bytes: bytes) -> Optional[bytes]:
    """`.awb` bytes → 16kHz mono s16le PCM bytes (실 ffmpeg). 실패 시 None."""
    fp = ffmpeg_path()
    if not fp:
        return None
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.awb"
        src.write_bytes(awb_bytes)
        try:
            out = subprocess.run(
                [fp, "-hide_banner", "-loglevel", "error", "-i", str(src),
                 "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
                capture_output=True, timeout=30)
            return out.stdout if out.returncode == 0 else None
        except Exception:  # noqa: BLE001
            return None


def check_decodable(awb_bytes: bytes, expected_ms: int, *, name: str = "audio",
                    tol_ms: int = 80) -> Optional[ValidationItem]:
    """서버 .awb 가 실 디코더로 기대 재생시간(±tol)으로 디코딩되는지 검증.

    ffmpeg 미가용 시 None(검증 스킵).
    """
    if not (ffmpeg_path() and amrwb_decoder_available()):
        return None
    pcm = decode_awb_pcm(awb_bytes)
    if pcm is None:
        return ValidationItem(category="AUDIO", name=f"{name}.decode", status="FAIL",
                              detail="ffmpeg AMR-WB 디코딩 실패(유효하지 않은 .awb)")
    actual_ms = len(pcm) // _BYTES_PER_MS
    ok = abs(actual_ms - expected_ms) <= tol_ms
    return ValidationItem(
        category="AUDIO", name=f"{name}.decode", status="PASS" if ok else "FAIL",
        expected=f"{expected_ms}ms±{tol_ms}", actual=f"{actual_ms}ms",
        detail=f"실 ffmpeg 디코딩 {len(pcm)}B PCM ({actual_ms}ms)")
