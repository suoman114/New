"""SIP UA 상태머신 (Call-ID 기반).

시뮬레이터는 caller 측 UA 를 구동하여 INVITE→(180/200)→ACK→…→BYE 시퀀스의
주입용 메시지를 생성한다. 상태: IDLE→INVITING→RINGING→CONNECTED→TERMINATING→TERMINATED.
IMS/MCPTT 공통이며, 호 흐름의 메시지 바이트는 tapper-feed 가 송신한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from . import messages as M


class UaState(str, Enum):
    IDLE = "IDLE"
    INVITING = "INVITING"
    RINGING = "RINGING"
    CONNECTED = "CONNECTED"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"


@dataclass
class CallerUA:
    """발신 UA. 호 1개(Call-ID)를 표현."""

    from_uri: str
    to_uri: str
    via_host: str
    via_port: int = 5060
    contact: Optional[str] = None
    call_id: str = field(default_factory=M.gen_call_id)
    from_tag: str = field(default_factory=M.gen_tag)
    to_tag: Optional[str] = None
    cseq: int = 1
    state: UaState = UaState.IDLE

    def __post_init__(self) -> None:
        if self.contact is None:
            self.contact = f"<sip:{self.from_uri}@{self.via_host}:{self.via_port}>"

    def invite(self, sdp: str = "") -> M.SipMessage:
        self.state = UaState.INVITING
        return M.build_invite(
            call_id=self.call_id, from_uri=self.from_uri, to_uri=self.to_uri,
            from_tag=self.from_tag, via_host=self.via_host, via_port=self.via_port,
            contact=self.contact, sdp=sdp, cseq=self.cseq,
        )

    def on_response(self, msg: M.SipMessage) -> None:
        """수신 응답 반영(상태 전이 + to-tag 학습)."""
        if not msg.is_request and msg.status:
            to = msg.get("To") or ""
            if "tag=" in to and self.to_tag is None:
                self.to_tag = to.split("tag=", 1)[1].split(";")[0]
            if msg.status == 180:
                self.state = UaState.RINGING
            elif 200 <= msg.status < 300:
                self.state = UaState.CONNECTED

    def ack(self) -> M.SipMessage:
        return M.build_ack(
            call_id=self.call_id, from_uri=self.from_uri, to_uri=self.to_uri,
            from_tag=self.from_tag, to_tag=self.to_tag or M.gen_tag(),
            via_host=self.via_host, via_port=self.via_port, cseq=self.cseq,
        )

    def bye(self) -> M.SipMessage:
        self.state = UaState.TERMINATING
        self.cseq += 1
        return M.build_bye(
            call_id=self.call_id, from_uri=self.from_uri, to_uri=self.to_uri,
            from_tag=self.from_tag, to_tag=self.to_tag or M.gen_tag(),
            via_host=self.via_host, via_port=self.via_port, cseq=self.cseq,
        )

    def terminated(self) -> None:
        self.state = UaState.TERMINATED
