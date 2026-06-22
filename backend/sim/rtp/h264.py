"""H.264 RTP payload 포맷 + de-interleaving (RFC6184 / 설계서 부록8·9).

지원:
  - Single NAL Unit (type 1~23)
  - STAP-A (type 24): aggregation packet
  - FU-A (type 28): fragmentation unit (S/E 로 재조립)
  - DON/AbsDON 계산(부록9): interleaved 모드 decoding order 복원
  - Annex B byte stream(.h264) 재구성 (start code 0x00000001 + NAL)

NAL header byte: F(1) NRI(2) Type(5).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

NAL_STAP_A = 24
NAL_FU_A = 28
ANNEXB_START = b"\x00\x00\x00\x01"


def nal_type(nal: bytes) -> int:
    return nal[0] & 0x1F


def nal_nri(nal: bytes) -> int:
    return (nal[0] >> 5) & 0x03


# ── 패킷화 (테스트/송출 보조) ─────────────────────────────────────────────────
def packetize_single(nal: bytes) -> bytes:
    """Single NAL Unit packet = NAL 그대로."""
    return nal


def packetize_stap_a(nals: list[bytes], *, nri: int = 3) -> bytes:
    """STAP-A: [STAP-A header][(16bit size)(NAL)]…  (모두 동일 timestamp)."""
    out = bytearray([(0 << 7) | ((nri & 0x03) << 5) | NAL_STAP_A])
    for n in nals:
        out += struct.pack("!H", len(n)) + n
    return bytes(out)


def packetize_fu_a(nal: bytes, mtu: int) -> list[bytes]:
    """FU-A: NAL 을 mtu 단위로 분할. 각 packet = [FU indicator][FU header][payload]."""
    header = nal[0]
    nri = (header >> 5) & 0x03
    typ = header & 0x1F
    body = nal[1:]
    indicator = (0 << 7) | (nri << 5) | NAL_FU_A
    chunk = max(1, mtu - 2)
    packets: list[bytes] = []
    pieces = [body[i:i + chunk] for i in range(0, len(body), chunk)] or [b""]
    for i, piece in enumerate(pieces):
        start = 1 if i == 0 else 0
        end = 1 if i == len(pieces) - 1 else 0
        fu_header = (start << 7) | (end << 6) | (0 << 5) | typ
        packets.append(bytes([indicator, fu_header]) + piece)
    return packets


# ── De-packetization ─────────────────────────────────────────────────────────
def depacketize(payloads: list[bytes]) -> list[bytes]:
    """RTP payload 리스트 → NAL unit 리스트 (FU-A 재조립, STAP-A 분해)."""
    nals: list[bytes] = []
    fu_buf: bytearray | None = None
    fu_hdr: int | None = None
    for p in payloads:
        if not p:
            continue
        t = p[0] & 0x1F
        if t == NAL_STAP_A:
            idx = 1
            while idx + 2 <= len(p):
                (size,) = struct.unpack("!H", p[idx:idx + 2])
                idx += 2
                nals.append(p[idx:idx + size])
                idx += size
        elif t == NAL_FU_A:
            indicator, fu_header = p[0], p[1]
            start = (fu_header >> 7) & 1
            end = (fu_header >> 6) & 1
            typ = fu_header & 0x1F
            if start:
                fu_hdr = (indicator & 0xE0) | typ
                fu_buf = bytearray([fu_hdr]) + p[2:]
            elif fu_buf is not None:
                fu_buf += p[2:]
            if end and fu_buf is not None:
                nals.append(bytes(fu_buf))
                fu_buf, fu_hdr = None, None
        else:
            nals.append(p)               # single NAL (1~23)
    return nals


def to_annexb(nals: list[bytes]) -> bytes:
    """NAL unit 리스트 → Annex B byte stream(.h264)."""
    out = bytearray()
    for n in nals:
        if not n:
            continue
        out += ANNEXB_START + n
    return bytes(out)


def drop_nri_zero(nals: list[bytes]) -> list[bytes]:
    """NRI=0 인 NALU drop (부록8 decoding rule)."""
    return [n for n in nals if n and nal_nri(n) != 0]


# ── DON / AbsDON (부록9, interleaved 모드 decoding order) ──────────────────────
def don_diff(don_m: int, don_n: int) -> int:
    """don_diff(m,n) — 16bit DON wrap-around 거리 (RFC6184 §5.5).

    설계서 부록9 의 DON(m)>DON(n) 분기는 부호 오타가 있어 RFC6184 기준으로 구현한다
    (m>n 분기 조건은 `DON(m)-DON(n) >= 32768`).
    """
    if don_m == don_n:
        return 0
    if don_m < don_n:
        if don_n - don_m < 32768:
            return don_n - don_m
        return -(don_m + 65536 - don_n)
    # don_m > don_n
    if don_m - don_n >= 32768:
        return 65536 - don_m + don_n
    return -(don_m - don_n)


def absdon_sequence(dons: list[int]) -> list[int]:
    """연이어 전송된 NAL unit 들의 DON → AbsDON 시퀀스 (RFC6184 §5.5, 부록9)."""
    if not dons:
        return []
    abs_list = [dons[0]]                  # AbsDON(0) = DON(0)
    for i in range(1, len(dons)):
        m, n = dons[i - 1], dons[i]
        a = abs_list[-1]
        if m == n:
            abs_list.append(a)
        elif m < n:
            if n - m < 32768:
                abs_list.append(a + (n - m))
            else:
                abs_list.append(a - (m + 65536 - n))
        else:  # m > n
            if m - n >= 32768:
                abs_list.append(a + (65536 - m + n))
            else:
                abs_list.append(a - (m - n))
    return abs_list


@dataclass
class NalWithDon:
    nal: bytes
    don: int


def deinterleave(units: list[NalWithDon]) -> list[bytes]:
    """수신 순서의 (NAL, DON) → AbsDON 오름차순(decoding order) NAL 리스트."""
    dons = [u.don for u in units]
    absd = absdon_sequence(dons)
    order = sorted(range(len(units)), key=lambda i: absd[i])
    return [units[i].nal for i in order]


# ── 결정론적 NAL 생성 (실 인코더 없는 환경의 골든 검증용) ──────────────────────
def synthetic_nals(count: int, *, seed: int = 1, nri: int = 3,
                   size: int = 40) -> list[bytes]:
    """재현 가능한 NAL unit 시퀀스(첫 NAL=SPS(7), 둘째=PPS(8), 이후 slice(1/5))."""
    import hashlib

    nals: list[bytes] = []
    for i in range(count):
        if i == 0:
            typ = 7          # SPS
        elif i == 1:
            typ = 8          # PPS
        elif i % 12 == 2:
            typ = 5          # IDR slice
        else:
            typ = 1          # non-IDR slice
        header = ((nri & 0x03) << 5) | typ
        body = hashlib.sha256(f"{seed}:{i}".encode()).digest()
        while len(body) < size:
            body += hashlib.sha256(body).digest()
        nals.append(bytes([header]) + body[:size])
    return nals
