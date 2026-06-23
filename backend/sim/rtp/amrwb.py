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


# ── Bandwidth-Efficient(BE) 모드: 바이트 정렬 없는 연속 bitstream ─────────────
class _BitWriter:
    def __init__(self) -> None:
        self._bits: list[int] = []

    def write(self, value: int, n: int) -> None:
        for i in range(n - 1, -1, -1):
            self._bits.append((value >> i) & 1)

    def write_bits_from(self, data: bytes, nbits: int) -> None:
        for i in range(nbits):
            self._bits.append((data[i // 8] >> (7 - (i % 8))) & 1)

    def to_bytes(self) -> bytes:
        out = bytearray()
        for i in range(0, len(self._bits), 8):
            chunk = self._bits[i:i + 8]
            chunk = chunk + [0] * (8 - len(chunk))     # 마지막 byte 0 padding
            b = 0
            for bit in chunk:
                b = (b << 1) | bit
            out.append(b)
        return bytes(out)


class _BitReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0
        self._end = len(data) * 8

    def read(self, n: int) -> int:
        v = 0
        for _ in range(n):
            bit = 0
            if self._pos < self._end:
                bit = (self._data[self._pos // 8] >> (7 - (self._pos % 8))) & 1
            v = (v << 1) | bit
            self._pos += 1
        return v

    def read_bytes(self, nbits: int) -> bytes:
        bits = [self.read(1) for _ in range(nbits)]
        out = bytearray()
        for i in range(0, len(bits), 8):
            chunk = bits[i:i + 8]
            chunk = chunk + [0] * (8 - len(chunk))
            b = 0
            for bit in chunk:
                b = (b << 1) | bit
            out.append(b)
        return bytes(out)


def packetize_be(frames: list[AmrFrame], *, cmr: int = CMR_NO_REQUEST) -> bytes:
    """Bandwidth-Efficient payload: CMR(4) + ToC(6×n) + speech bits (연속, 끝 0 padding)."""
    w = _BitWriter()
    w.write(cmr & 0x0F, 4)
    if not frames:
        return w.to_bytes()
    for i, fr in enumerate(frames):
        f = 0 if i == len(frames) - 1 else 1
        w.write(f, 1)
        w.write(fr.ft & 0x0F, 4)
        w.write(fr.q & 1, 1)
    for fr in frames:
        if fr.is_speech or fr.is_sid:
            nbits = AMRWB_SPEECH_BITS[fr.ft]
            need = amrwb_frame_bytes(fr.ft)
            data = fr.data[:need].ljust(need, b"\x00")
            w.write_bits_from(data, nbits)
    return w.to_bytes()


def parse_be(payload: bytes) -> list[AmrFrame]:
    """BE payload → frame 리스트."""
    if not payload:
        return []
    r = _BitReader(payload)
    r.read(4)                                          # CMR skip
    tocs: list[tuple[int, int]] = []
    while True:
        f = r.read(1)
        ft = r.read(4)
        q = r.read(1)
        tocs.append((ft, q))
        if f == 0:
            break
        if r._pos >= r._end:                           # 방어적 종료
            break
    frames: list[AmrFrame] = []
    for ft, q in tocs:
        if ft <= 8 or ft == SID_FT_WB:
            data = r.read_bytes(AMRWB_SPEECH_BITS[ft])
            frames.append(AmrFrame(ft=ft, data=data, q=q))
        else:
            frames.append(AmrFrame(ft=ft, data=b"", q=q))
    return frames


def parse_storage(data: bytes, *, wb: bool = True) -> list[AmrFrame]:
    """File Storage(.awb/.amr) byte 열 → frame 리스트 (magic 이후 record 파싱).

    ffmpeg/opencore 가 인코딩한 실 음원 .awb 를 우리 frame 모델로 역파싱할 때 사용.
    """
    magic = b"#!AMR-WB\n" if wb else b"#!AMR\n"
    body = data[len(magic):] if data.startswith(magic) else data
    frames: list[AmrFrame] = []
    i = 0
    while i < len(body):
        h = body[i]
        ft = (h >> 3) & 0x0F
        q = (h >> 2) & 1
        i += 1
        n = amrwb_frame_bytes(ft) if ft <= 9 else 0
        frames.append(AmrFrame(ft=ft, data=bytes(body[i:i + n]), q=q))
        i += n
    return frames


def packetize(frames: list[AmrFrame], *, octet_align: bool = True,
              cmr: int = CMR_NO_REQUEST) -> bytes:
    """octet_align 에 따라 OA/BE payload 생성."""
    return packetize_oa(frames, cmr=cmr) if octet_align else packetize_be(frames, cmr=cmr)


def parse(payload: bytes, *, octet_align: bool = True) -> list[AmrFrame]:
    return parse_oa(payload) if octet_align else parse_be(payload)
