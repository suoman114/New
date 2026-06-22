"""SDP 빌더/파서 (RFC4566 + 설계서 부록1 + as-built).

지원: AMR-WB/16000, AMR/8000, telephone-event, H264/90000.
파싱 규칙: docs/specs/sip-sdp.md §3, 실제 필드: observed-from-logs.md §6
  - c=IN IP4 <ip>[/ttl]
  - m=<media> <port> <proto> <fmt...>   (오디오/ MCPTT application 라인)
  - a=rtpmap:<pt> <name>/<clock>[/<channels>]
  - a=fmtp:<pt> octet-align=1;mode-set=8;mode-change-capability=2;max-red=0
  - a=sendrecv|sendonly|recvonly, a=ptime, a=maxptime
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

_DIRECTIONS = {"sendrecv", "sendonly", "recvonly", "inactive"}


@dataclass
class RtpMap:
    pt: int
    name: str           # AMR-WB / AMR / telephone-event / H264
    clock: int          # 16000 / 8000 / 90000
    channels: Optional[int] = None


@dataclass
class SdpMedia:
    media: str          # "audio" | "video" | "application"
    port: int
    proto: str          # "RTP/AVP" | "UDP" ...
    fmts: list[str] = field(default_factory=list)         # payload types / "MCPTT"
    rtpmaps: dict[int, RtpMap] = field(default_factory=dict)
    fmtp: dict[int, dict[str, str]] = field(default_factory=dict)
    direction: str = "sendrecv"
    ptime: Optional[int] = None
    maxptime: Optional[int] = None

    def primary_audio(self) -> Optional[RtpMap]:
        """AMR-WB > AMR 우선의 주 오디오 코덱."""
        for want in ("AMR-WB", "AMR"):
            for rm in self.rtpmaps.values():
                if rm.name.upper() == want:
                    return rm
        # telephone-event 제외한 첫 코덱
        for rm in self.rtpmaps.values():
            if rm.name.upper() != "TELEPHONE-EVENT":
                return rm
        return None

    def is_octet_aligned(self, pt: int) -> bool:
        return self.fmtp.get(pt, {}).get("octet-align") == "1"

    def mode_set(self, pt: int) -> list[int]:
        raw = self.fmtp.get(pt, {}).get("mode-set")
        if not raw:
            return []
        return [int(x) for x in raw.split(",") if x.strip().isdigit()]


@dataclass
class Sdp:
    ip: str = "127.0.0.1"
    origin: str = "- 0 0 IN IP4 127.0.0.1"
    session_name: str = "-"
    medias: list[SdpMedia] = field(default_factory=list)
    bandwidth: list[str] = field(default_factory=list)   # 예: ["AS:41","RS:0","RR:2500"]

    def audio(self) -> Optional[SdpMedia]:
        for m in self.medias:
            if m.media == "audio":
                return m
        return None

    def has_mcptt_app(self) -> bool:
        return any(m.media == "application" and "MCPTT" in m.fmts for m in self.medias)


def parse_sdp(text: str) -> Sdp:
    """SDP 문자열 파싱. \\r\\n / \\n 모두 허용."""
    sdp = Sdp()
    cur: Optional[SdpMedia] = None
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or "=" not in line:
            continue
        typ, val = line.split("=", 1)
        if typ == "o":
            sdp.origin = val
        elif typ == "s":
            sdp.session_name = val
        elif typ == "c":
            # c=IN IP4 1.2.3.4[/ttl]
            parts = val.split()
            if len(parts) >= 3:
                ip = parts[2].split("/")[0]
                if cur is None:
                    sdp.ip = ip
        elif typ == "b":
            sdp.bandwidth.append(val)
        elif typ == "m":
            parts = val.split()
            cur = SdpMedia(media=parts[0], port=int(parts[1]), proto=parts[2],
                           fmts=parts[3:])
            sdp.medias.append(cur)
        elif typ == "a" and cur is not None:
            _parse_attr(val, cur)
        elif typ == "a" and cur is None:
            pass
    return sdp


def _parse_attr(val: str, media: SdpMedia) -> None:
    if val in _DIRECTIONS:
        media.direction = val
        return
    key, _, rest = val.partition(":")
    if key == "rtpmap":
        # 100 AMR-WB/16000/1
        pt_s, _, desc = rest.partition(" ")
        comps = desc.split("/")
        rm = RtpMap(pt=int(pt_s), name=comps[0],
                    clock=int(comps[1]) if len(comps) > 1 else 0,
                    channels=int(comps[2]) if len(comps) > 2 else None)
        media.rtpmaps[rm.pt] = rm
    elif key == "fmtp":
        pt_s, _, params = rest.partition(" ")
        d: dict[str, str] = {}
        for tok in params.replace(" ", "").split(";"):
            if not tok:
                continue
            k, _, v = tok.partition("=")
            d[k] = v if v != "" else "1"
        media.fmtp[int(pt_s)] = d
    elif key == "ptime":
        media.ptime = int(rest)
    elif key == "maxptime":
        media.maxptime = int(rest)


def build_sdp(sdp: Sdp) -> str:
    """Sdp → 문자열 (\\r\\n 종단)."""
    lines = ["v=0", f"o={sdp.origin}", f"s={sdp.session_name}", f"c=IN IP4 {sdp.ip}"]
    for b in sdp.bandwidth:
        lines.append(f"b={b}")
    lines.append("t=0 0")
    for m in sdp.medias:
        lines.append(f"m={m.media} {m.port} {m.proto} {' '.join(map(str, m.fmts))}")
        for pt, rm in m.rtpmaps.items():
            ch = f"/{rm.channels}" if rm.channels else ""
            lines.append(f"a=rtpmap:{pt} {rm.name}/{rm.clock}{ch}")
            if pt in m.fmtp:
                params = ";".join(f"{k}={v}" for k, v in m.fmtp[pt].items())
                lines.append(f"a=fmtp:{pt} {params}")
        if m.ptime is not None:
            lines.append(f"a=ptime:{m.ptime}")
        if m.maxptime is not None:
            lines.append(f"a=maxptime:{m.maxptime}")
        lines.append(f"a={m.direction}")
    return "\r\n".join(lines) + "\r\n"


def amrwb_offer(ip: str, port: int, *, pt: int = 98, mode_set: int = 8,
                direction: str = "sendrecv") -> Sdp:
    """AMR-WB 단일 코덱 오퍼 SDP (테스트/시나리오 기본)."""
    media = SdpMedia(media="audio", port=port, proto="RTP/AVP", fmts=[str(pt)],
                     direction=direction, ptime=20, maxptime=240)
    media.rtpmaps[pt] = RtpMap(pt=pt, name="AMR-WB", clock=16000, channels=1)
    media.fmtp[pt] = {"octet-align": "1", "mode-set": str(mode_set)}
    return Sdp(ip=ip, origin=f"- 12 1000 IN IP4 {ip}", session_name="QC VOIP",
               medias=[media])
