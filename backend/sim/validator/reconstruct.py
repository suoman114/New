"""송출 frame → 골든 File Storage(.awb/.amr) 재구성 (설계서 부록4/5).

검증기는 우리가 송출한 frame 으로 서버가 저장해야 할 파일을 재구성하여 byte 비교한다.
규칙(부록5):
  - magic header 기록 (#!AMR-WB\\n / #!AMR\\n)
  - speech frame(FT<=8): storage record = [header(FT<<3|Q<<2)] + speech bytes(byte-align)
  - SID(FT=9 WB / 8 NB) / NO_DATA / SPEECH_LOST: 묵음 packet 으로 변환(부록7, write_mute)

1차 구현은 talk-spurt(연속 speech) 와 단발 SID/NO_DATA 치환을 정확히 처리한다.
연속 SID 의 timestamp-gap 채움(부록5의 nNOWTIMESTAMP-nOLDTIMESTAMP)은 v2 확장(아래 주석).
"""

from __future__ import annotations

from ..rtp.amrwb import AmrFrame, SID_FT_WB, amrwb_frame_bytes
from .silence_tables import write_mute

MAGIC_AMRWB = b"#!AMR-WB\n"
MAGIC_AMR = b"#!AMR\n"


def storage_record(frame: AmrFrame) -> bytes:
    """speech/SID frame 1개의 storage record (header + speech bytes)."""
    n = amrwb_frame_bytes(frame.ft)
    header = ((frame.ft & 0x0F) << 3) | ((frame.q & 1) << 2)
    data = frame.data[:n].ljust(n, b"\x00")
    return bytes([header]) + data


def reconstruct_awb(frames: list[AmrFrame], *, mode_set_max: int = 8,
                    wb: bool = True) -> bytes:
    """frame 리스트 → 골든 .awb/.amr bytes."""
    out = bytearray(MAGIC_AMRWB if wb else MAGIC_AMR)
    for fr in frames:
        if fr.ft <= 8:
            out += storage_record(fr)
        elif fr.ft == SID_FT_WB:
            # SID → 묵음 1개 (연속 SID timestamp-gap 채움은 v2)
            out += write_mute(1, wb=wb, mode=mode_set_max)
        else:
            # NO_DATA(15) / SPEECH_LOST(14) → 묵음 1개
            out += write_mute(1, wb=wb, mode=mode_set_max)
    return bytes(out)


def frame_count_of(awb_bytes: bytes, *, mode_set_max: int = 8, wb: bool = True) -> int:
    """재구성 파일의 speech/mute record 개수(검증 보조)."""
    body = awb_bytes[len(MAGIC_AMRWB if wb else MAGIC_AMR):]
    idx = 0
    count = 0
    while idx < len(body):
        header = body[idx]
        ft = (header >> 3) & 0x0F
        n = amrwb_frame_bytes(ft) if ft <= 9 else len(write_mute(1, wb=wb, mode=mode_set_max)) - 1
        idx += 1 + n
        count += 1
    return count
