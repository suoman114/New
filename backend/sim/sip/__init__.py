"""sip-engine: SIP UA/메시지/SDP, IMS·McPTT call flow.

권위 스펙: docs/specs/sip-sdp.md, observed-from-logs.md §6.
"""

from typing import Optional

from ..platform.models import FlowEvent
from . import messages as messages
from . import sdp as sdp
from .messages import SipMessage
from .sdp import Sdp, SdpMedia, RtpMap, parse_sdp, build_sdp, amrwb_offer
from .ua import CallerUA, UaState

__all__ = [
    "messages", "sdp", "SipMessage",
    "Sdp", "SdpMedia", "RtpMap", "parse_sdp", "build_sdp", "amrwb_offer",
    "CallerUA", "UaState", "sip_flow_event",
]


def sip_flow_event(msg: SipMessage, *, session_id: str, direction: str,
                   peer: str, call_id: Optional[str] = None) -> FlowEvent:
    """SipMessage → ladder 용 FlowEvent (payload 에 헤더/raw 보존)."""
    if msg.is_request:
        label = msg.method or "REQ"
        summary = f"{msg.method} {msg.ruri}"
    else:
        label = f"{msg.status} {msg.reason}"
        summary = label
    return FlowEvent(
        session_id=session_id,
        call_id=call_id or msg.call_id,
        channel="SIP",
        direction=direction,
        peer=peer,
        label=label,
        summary=summary,
        payload={
            "start_line": summary,
            "headers": dict(msg.headers),
            "body": msg.body,
            "raw": msg.serialize().decode("utf-8", "replace"),
        },
    )
