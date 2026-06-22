"""AMR-WB frame → RTP 패킷 시퀀스 생성 + 송출 통계.

1 frame = 1 RTP packet(20ms) 기본. seq++ / timestamp += 320(16kHz 20ms) / SSRC 일관.
통계는 VCMM "Recording statistics"(observed-from-logs.md §5)와 같은 형식으로 산출하여
검증기 골든 비교에 사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .amrwb import AmrFrame, SAMPLES_PER_FRAME_WB, SID_FT_WB, packetize_oa
from .rtp import RtpPacket


@dataclass
class StreamStats:
    first_seq: int | None = None
    last_seq: int | None = None
    first_ts: int | None = None
    last_ts: int | None = None
    ssrc: int = 0
    total_packets: int = 0
    sid_count: int = 0
    play_time_ms: int = 0


@dataclass
class AmrWbStream:
    """하나의 RTP 스트림(한 발언/한 레그)."""

    ssrc: int
    payload_type: int = 98
    start_seq: int = 0
    start_ts: int = 0
    samples_per_frame: int = SAMPLES_PER_FRAME_WB
    _frames: list[AmrFrame] = field(default_factory=list)

    def build(self, frames: list[AmrFrame]) -> list[RtpPacket]:
        """frame 리스트 → RTP 패킷 리스트 (1 frame/packet)."""
        self._frames = list(frames)
        packets: list[RtpPacket] = []
        seq = self.start_seq
        ts = self.start_ts
        for i, fr in enumerate(frames):
            payload = packetize_oa([fr])
            packets.append(RtpPacket(
                payload_type=self.payload_type,
                sequence=seq & 0xFFFF,
                timestamp=ts & 0xFFFFFFFF,
                ssrc=self.ssrc,
                payload=payload,
                marker=(i == 0),               # talk spurt 시작 marker
            ))
            seq += 1
            ts += self.samples_per_frame
        return packets

    def stats(self, packets: list[RtpPacket]) -> StreamStats:
        """송출 패킷의 기대 통계(검증기 골든)."""
        st = StreamStats(ssrc=self.ssrc, total_packets=len(packets))
        if not packets:
            return st
        st.first_seq = packets[0].sequence
        st.last_seq = packets[-1].sequence
        st.first_ts = packets[0].timestamp
        st.last_ts = packets[-1].timestamp
        st.sid_count = sum(1 for f in self._frames if f.ft == SID_FT_WB)
        # playTime: frame 수 × 20ms (VCMM 통계와 동일 개념)
        st.play_time_ms = len(packets) * (self.samples_per_frame * 1000 // 16000)
        return st
