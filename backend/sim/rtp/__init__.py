"""rtp-media: RTP + AMR-WB 패킷화/송출, 묵음/손실/지터.

권위 스펙: docs/specs/amr-wb-rtp.md(부록2~7), silence-packets.md.
"""

from ..platform.models import FlowEvent
from .amrwb import (
    AmrFrame,
    AMRWB_SPEECH_BITS,
    amrwb_frame_bytes,
    packetize_oa,
    parse_oa,
    toc_byte,
)
from .rtp import RtpPacket
from .sender import AmrWbStream, StreamStats
from . import encoder as encoder
from . import impair as impair

__all__ = [
    "AmrFrame", "AMRWB_SPEECH_BITS", "amrwb_frame_bytes", "packetize_oa", "parse_oa",
    "toc_byte", "RtpPacket", "AmrWbStream", "StreamStats", "encoder", "impair",
    "rtp_stat_event",
]


def rtp_stat_event(stats: StreamStats, *, session_id: str, call_id: str,
                   peer: str = "VCMM_0", dropped: int = 0) -> FlowEvent:
    """RTP 송출 요약 → FlowEvent(channel=RTP). 패킷 단위 폭주 대신 요약 1건."""
    return FlowEvent(
        session_id=session_id,
        call_id=call_id,
        channel="RTP",
        direction="SIM->SUT",
        peer=peer,
        label="RTP stream",
        summary=(f"pkts={stats.total_packets} seq={stats.first_seq}~{stats.last_seq} "
                 f"ssrc={stats.ssrc} sid={stats.sid_count} drop={dropped} "
                 f"play={stats.play_time_ms}ms"),
        payload={
            "first_seq": stats.first_seq, "last_seq": stats.last_seq,
            "first_ts": stats.first_ts, "last_ts": stats.last_ts,
            "ssrc": stats.ssrc, "total_packets": stats.total_packets,
            "sid_count": stats.sid_count, "dropped_packets": dropped,
            "play_time_ms": stats.play_time_ms,
        },
    )
