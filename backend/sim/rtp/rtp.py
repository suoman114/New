"""RTP 헤더 패킹/언패킹 (RFC3550, 설계서 부록2).

검증 포인트: V=2, PT=nego, SSRC 일관, seq 정렬, timestamp 증가분.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

_RTP_VERSION = 2


@dataclass
class RtpPacket:
    payload_type: int
    sequence: int
    timestamp: int
    ssrc: int
    payload: bytes = b""
    marker: bool = False
    padding: bool = False
    extension: bool = False
    csrc: list[int] = field(default_factory=list)

    def pack(self) -> bytes:
        cc = len(self.csrc) & 0x0F
        b0 = (_RTP_VERSION << 6) | (int(self.padding) << 5) | (int(self.extension) << 4) | cc
        b1 = (int(self.marker) << 7) | (self.payload_type & 0x7F)
        header = struct.pack("!BBHII", b0, b1, self.sequence & 0xFFFF,
                             self.timestamp & 0xFFFFFFFF, self.ssrc & 0xFFFFFFFF)
        for c in self.csrc:
            header += struct.pack("!I", c & 0xFFFFFFFF)
        return header + self.payload

    @classmethod
    def unpack(cls, data: bytes) -> "RtpPacket":
        if len(data) < 12:
            raise ValueError("RTP packet too short")
        b0, b1, seq, ts, ssrc = struct.unpack("!BBHII", data[:12])
        version = b0 >> 6
        if version != _RTP_VERSION:
            raise ValueError(f"unexpected RTP version {version}")
        cc = b0 & 0x0F
        offset = 12
        csrc = []
        for _ in range(cc):
            (c,) = struct.unpack("!I", data[offset:offset + 4])
            csrc.append(c)
            offset += 4
        return cls(
            payload_type=b1 & 0x7F,
            sequence=seq,
            timestamp=ts,
            ssrc=ssrc,
            payload=data[offset:],
            marker=bool(b1 & 0x80),
            padding=bool(b0 & 0x20),
            extension=bool(b0 & 0x10),
            csrc=csrc,
        )
