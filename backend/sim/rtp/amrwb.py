"""AMR / AMR-WB RTP payload 패킷화 (설계서 부록3/6).

구조: payload header(CMR) → ToC(F/FT/Q) → speech data.
1차 구현은 실제 SDP 가 쓰는 **Octet-Aligned(OA) 모드**를 완전 지원한다(octet-align=1).
Bandwidth-Efficient(BE) 모드는 2차 (validator 재구성은 부록5 의사코드로 양쪽 처리).

FT(AMR-WB): 0..8=speech modes, 9=SID, 10..13=reserved, 14=SPEECH_LOST, 15=NO_DATA.
"""

from __future__ import annotations

from dataclasses import dataclass

# 부록 6: AMR-WB speech frame bit 길이 (FT 0..8 + SID(9))
AMRWB_SPEECH_BITS = (132, 177, 253, 285, 317, 365, 397, 461, 477, 40)
AMR_SPEECH_BITS = (95, 103, 118, 134, 148, 159, 204, 244, 39)

SID_FT_WB = 9
NO_DATA_WB = 15
SPEECH_LOST_WB = 14
SAMPLES_PER_FRAME_WB = 320   # 20ms @ 16kHz
SAMPLES_PER_FRAME_NB = 160   # 20ms @ 8kHz

CMR_NO_REQUEST = 0xF         # 변경 요청 없음


def amrwb_frame_bytes(ft: int) -> int:
    """OA 모드에서 한 speech frame 의 byte 길이 (byte-align, 부록6)."""
    if ft <= 9:
        return (AMRWB_SPEECH_BITS[ft] + 7) // 8
    # 10..13 reserved, 14/15 no data
    return 0


@dataclass
class AmrFrame:
    """하나의 speech frame: FT + (byte-aligned) speech data."""

    ft: int
    data: bytes = b""
    q: int = 1               # 1=정상, 0=손상

    @property
    def is_speech(self) -> bool:
        return self.ft <= 8

    @property
    def is_sid(self) -> bool:
        return self.ft == SID_FT_WB

    @property
    def is_no_data(self) -> bool:
        return self.ft >= SPEECH_LOST_WB


def toc_byte(ft: int, q: int, last: bool) -> int:
    """OA ToC 1 byte: F(1) FT(4) Q(1) + 2bit padding."""
    f = 0 if last else 1
    return (f << 7) | ((ft & 0x0F) << 3) | ((q & 1) << 2)


def packetize_oa(frames: list[AmrFrame], *, cmr: int = CMR_NO_REQUEST) -> bytes:
    """Octet-Aligned 모드 payload 생성: [CMR][ToC...][speech...]."""
    if not frames:
        return bytes([(cmr & 0x0F) << 4])
    out = bytearray()
    out.append((cmr & 0x0F) << 4)                 # CMR byte (high nibble)
    for i, fr in enumerate(frames):
        out.append(toc_byte(fr.ft, fr.q, last=(i == len(frames) - 1)))
    for fr in frames:
        if fr.is_speech or fr.is_sid:
            need = amrwb_frame_bytes(fr.ft)
            data = fr.data[:need].ljust(need, b"\x00")
            out += data
    return bytes(out)


def parse_oa(payload: bytes) -> list[AmrFrame]:
    """OA payload → frame 리스트 (역검증/테스트용)."""
    if len(payload) < 1:
        return []
    idx = 1                                        # CMR byte skip
    tocs: list[tuple[int, int]] = []               # (ft, q)
    while idx < len(payload):
        b = payload[idx]
        idx += 1
        ft = (b >> 3) & 0x0F
        q = (b >> 2) & 1
        tocs.append((ft, q))
        if (b & 0x80) == 0:                        # F=0 → last
            break
    frames: list[AmrFrame] = []
    for ft, q in tocs:
        n = amrwb_frame_bytes(ft) if ft <= 8 or ft == SID_FT_WB else 0
        data = payload[idx:idx + n]
        idx += n
        frames.append(AmrFrame(ft=ft, data=bytes(data), q=q))
    return frames
