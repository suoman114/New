"""pcap_mirror 주입 모드 — L3/UDP 패킷을 인터페이스에 주입(실 VCTP libpcap 미러 대상).

tapper_udp 가 VCSM/VCMM 포트로 직접 UDP 송신(VCTP 우회)인 반면, pcap_mirror 는
**완전한 IP/UDP 패킷을 NIC 에 주입**하여 실 VCTP 가 libpcap 으로 미러 캡처하도록 한다
(src IP 를 실 호 단말 주소로 위장 가능). scapy 가 필요하며 root 권한으로 동작한다.

Feeder Protocol(engine) 과 동일 시그니처라 ScenarioEngine 에 그대로 주입할 수 있다.
"""

from __future__ import annotations

import asyncio
import random
from typing import Optional

from ..platform.config import TapperConfig
from ..platform.eventbus import EventBus
from ..platform.models import FlowEvent
from ..rtp.rtp import RtpPacket


def scapy_available() -> bool:
    try:
        import scapy  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


class PcapFeeder:
    """scapy L3 소켓으로 IP/UDP 패킷을 주입하는 Tapper(미러) 송신기."""

    def __init__(self, cfg: TapperConfig, *, iface: str = "lo",
                 src_ip: str = "127.0.0.1", bus: Optional[EventBus] = None) -> None:
        self._cfg = cfg
        self._iface = iface
        self._src_ip = src_ip
        self._bus = bus
        self._sock = None
        self.sent_sip = 0
        self.sent_rtp = 0

    def _open(self) -> None:
        from scapy.all import conf
        self._sock = conf.L3socket(iface=self._iface)

    async def start(self) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self._open)

    async def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _build(self, payload: bytes, dst_ip: str, dst_port: int):
        from scapy.all import IP, UDP, Raw
        return (IP(src=self._src_ip, dst=dst_ip)
                / UDP(sport=random.randint(20000, 60000), dport=dst_port)
                / Raw(load=payload))

    def _send(self, pkt) -> None:
        if self._sock is None:
            self._open()
        self._sock.send(pkt)

    async def send_sip(self, data: bytes, *, event: Optional[FlowEvent] = None,
                       session_id: str = "", call_id: str = "", label: str = "SIP") -> None:
        pkt = self._build(data, self._cfg.sip_host, self._cfg.sip_port)
        await asyncio.get_running_loop().run_in_executor(None, self._send, pkt)
        self.sent_sip += 1
        if self._bus is not None:
            await self._bus.publish(event or FlowEvent(
                session_id=session_id, call_id=call_id or None, channel="SIP",
                direction="SIM->SUT", peer="VCTP", label=label,
                summary=f"pcap→{self._iface} {self._src_ip}→{self._cfg.sip_host}:"
                        f"{self._cfg.sip_port} ({len(data)}B)",
                payload={"bytes": len(data), "iface": self._iface}))

    async def send_rtp(self, packet: RtpPacket, port: int, *,
                       session_id: str = "", call_id: str = "") -> None:
        pkt = self._build(packet.pack(), self._cfg.rtp_host, port)
        await asyncio.get_running_loop().run_in_executor(None, self._send, pkt)
        self.sent_rtp += 1
