"""SIP 메시지 빌더/파서/직렬화 (RFC3261 라인 포맷).

시뮬레이터는 Tapper 가 미러링한 SIP 를 주입하므로 요청/응답 양방향을 생성한다.
지원 메서드(observed-from-logs.md §6): INVITE/ACK/BYE/REGISTER/SUBSCRIBE/NOTIFY/
UPDATE/OPTIONS/MESSAGE + 응답(100/180/200/401/408/481 등).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

CRLF = "\r\n"


@dataclass
class SipMessage:
    is_request: bool
    method: Optional[str] = None        # 요청일 때
    ruri: Optional[str] = None          # 요청일 때 Request-URI
    status: Optional[int] = None        # 응답일 때
    reason: Optional[str] = None        # 응답일 때
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: str = ""

    # ── 헤더 접근 ──
    def add(self, name: str, value: str) -> "SipMessage":
        self.headers.append((name, value))
        return self

    def get(self, name: str) -> Optional[str]:
        low = name.lower()
        for n, v in self.headers:
            if n.lower() == low:
                return v
        return None

    def get_all(self, name: str) -> list[str]:
        low = name.lower()
        return [v for n, v in self.headers if n.lower() == low]

    @property
    def call_id(self) -> Optional[str]:
        return self.get("Call-ID")

    @property
    def cseq(self) -> Optional[str]:
        return self.get("CSeq")

    def serialize(self) -> bytes:
        if self.is_request:
            start = f"{self.method} {self.ruri} SIP/2.0"
        else:
            start = f"SIP/2.0 {self.status} {self.reason}"
        lines = [start]
        headers = list(self.headers)
        # Content-Length 자동 보정
        if not any(n.lower() == "content-length" for n, _ in headers):
            headers.append(("Content-Length", str(len(self.body.encode("utf-8")))))
        for n, v in headers:
            lines.append(f"{n}: {v}")
        return (CRLF.join(lines) + CRLF + CRLF + self.body).encode("utf-8")

    @classmethod
    def parse(cls, data: bytes | str) -> "SipMessage":
        text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
        head, _, body = text.partition(CRLF + CRLF)
        lines = head.split(CRLF)
        start = lines[0]
        if start.startswith("SIP/2.0"):
            _, status, reason = start.split(" ", 2)
            msg = cls(is_request=False, status=int(status), reason=reason)
        else:
            method, ruri, _ = start.split(" ", 2)
            msg = cls(is_request=True, method=method, ruri=ruri)
        for line in lines[1:]:
            if ":" in line:
                n, v = line.split(":", 1)
                msg.add(n.strip(), v.strip())
        msg.body = body
        return msg


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────
def gen_call_id(host: str = "sim.uangel.com") -> str:
    return f"{uuid.uuid4().hex}@{host}"


def gen_tag() -> str:
    return uuid.uuid4().hex[:8]


def gen_branch() -> str:
    return "z9hG4bK" + uuid.uuid4().hex[:16]


def build_invite(*, call_id: str, from_uri: str, to_uri: str, from_tag: str,
                 via_host: str, via_port: int, contact: str, sdp: str = "",
                 cseq: int = 1, ruri: Optional[str] = None,
                 extra_headers: Optional[list[tuple[str, str]]] = None) -> SipMessage:
    msg = SipMessage(is_request=True, method="INVITE", ruri=ruri or to_uri)
    msg.add("Via", f"SIP/2.0/UDP {via_host}:{via_port};branch={gen_branch()}")
    msg.add("Max-Forwards", "70")
    msg.add("From", f"{from_uri};tag={from_tag}")
    msg.add("To", to_uri)
    msg.add("Call-ID", call_id)
    msg.add("CSeq", f"{cseq} INVITE")
    msg.add("Contact", contact)
    for n, v in (extra_headers or []):
        msg.add(n, v)
    if sdp:
        msg.add("Content-Type", "application/sdp")
    msg.body = sdp
    return msg


def build_response(request: SipMessage, status: int, reason: str, *,
                   to_tag: Optional[str] = None, contact: Optional[str] = None,
                   sdp: str = "") -> SipMessage:
    """요청에 대한 응답 생성 (Via/From/To/Call-ID/CSeq 반향)."""
    msg = SipMessage(is_request=False, status=status, reason=reason)
    for v in request.get_all("Via"):
        msg.add("Via", v)
    frm = request.get("From") or ""
    to = request.get("To") or ""
    if to_tag and "tag=" not in to:
        to = f"{to};tag={to_tag}"
    msg.add("From", frm)
    msg.add("To", to)
    if request.call_id:
        msg.add("Call-ID", request.call_id)
    if request.cseq:
        msg.add("CSeq", request.cseq)
    if contact:
        msg.add("Contact", contact)
    if sdp:
        msg.add("Content-Type", "application/sdp")
    msg.body = sdp
    return msg


def build_ack(*, call_id: str, from_uri: str, to_uri: str, from_tag: str, to_tag: str,
              via_host: str, via_port: int, cseq: int = 1,
              ruri: Optional[str] = None) -> SipMessage:
    msg = SipMessage(is_request=True, method="ACK", ruri=ruri or to_uri)
    msg.add("Via", f"SIP/2.0/UDP {via_host}:{via_port};branch={gen_branch()}")
    msg.add("Max-Forwards", "70")
    msg.add("From", f"{from_uri};tag={from_tag}")
    msg.add("To", f"{to_uri};tag={to_tag}")
    msg.add("Call-ID", call_id)
    msg.add("CSeq", f"{cseq} ACK")
    return msg


def build_bye(*, call_id: str, from_uri: str, to_uri: str, from_tag: str, to_tag: str,
              via_host: str, via_port: int, cseq: int = 2,
              ruri: Optional[str] = None) -> SipMessage:
    msg = SipMessage(is_request=True, method="BYE", ruri=ruri or to_uri)
    msg.add("Via", f"SIP/2.0/UDP {via_host}:{via_port};branch={gen_branch()}")
    msg.add("Max-Forwards", "70")
    msg.add("From", f"{from_uri};tag={from_tag}")
    msg.add("To", f"{to_uri};tag={to_tag}")
    msg.add("Call-ID", call_id)
    msg.add("CSeq", f"{cseq} BYE")
    return msg
