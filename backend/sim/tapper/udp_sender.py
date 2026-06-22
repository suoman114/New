"""Tapper UDP 포워딩 모방 송신기.

시뮬레이터가 VCTP 하류 역할로 직접 주입(inject_mode=tapper_udp):
  - SIP → VCSM (cfg.tapper.sip_host:sip_port, 기본 127.0.0.1:10000)
  - RTP → VCMM (cfg.tapper.rtp_host:port, 기본 10001~11000)
페이로드 내용은 가공하지 않는다. 송신 이벤트는 EventBus 로 발행(RTP 는 요약).
"""

from __future__ import annotations

import asyncio
from typing import Optional

from ..platform.config import TapperConfig
from ..platform.eventbus import EventBus
from ..platform.models import FlowEvent
from ..rtp.rtp import RtpPacket


class _UdpProto(asyncio.DatagramProtocol):
    def error_received(self, exc: Exception) -> None:  # pragma: no cover
        pass


class TapperFeeder:
    """비동기 UDP 송신기. SIP/RTP 분리 전송."""

    def __init__(self, cfg: TapperConfig, bus: Optional[EventBus] = None) -> None:
        self._cfg = cfg
        self._bus = bus
        self._transport: Optional[asyncio.DatagramTransport] = None
        self.sent_sip = 0
        self.sent_rtp = 0

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        # 로컬 임의 포트에 바인드한 비연결 UDP 소켓 → sendto 로 SIP/RTP 분리 전송
        self._transport, _ = await loop.create_datagram_endpoint(
            _UdpProto, local_addr=("0.0.0.0", 0))

    async def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def _ensure(self) -> asyncio.DatagramTransport:
        if self._transport is None:
            raise RuntimeError("TapperFeeder.start() 를 먼저 호출하세요.")
        return self._transport

    async def send_sip(self, data: bytes, *, event: Optional[FlowEvent] = None,
                       session_id: str = "", call_id: str = "", label: str = "SIP") -> None:
        """SIP 메시지를 VCSM 으로 송신.

        `event` 가 주어지면(상위 sip-engine 의 풍부한 sip_flow_event) 그것을 발행하고,
        없으면 기본 요약 이벤트를 발행한다 (이벤트 중복 방지).
        """
        self._ensure().sendto(data, (self._cfg.sip_host, self._cfg.sip_port))
        self.sent_sip += 1
        await self._emit(event or FlowEvent(
            session_id=session_id, call_id=call_id or None, channel="SIP",
            direction="SIM->SUT", peer="VCSM", label=label,
            summary=f"SIP→VCSM {self._cfg.sip_host}:{self._cfg.sip_port} ({len(data)}B)",
            payload={"bytes": len(data)},
        ))

    async def send_rtp(self, packet: RtpPacket, port: int, *,
                       session_id: str = "", call_id: str = "") -> None:
        """RTP 패킷을 VCMM 의 지정 포트로 송신(요약 이벤트는 호출측에서)."""
        self._ensure().sendto(packet.pack(), (self._cfg.rtp_host, port))
        self.sent_rtp += 1

    async def _emit(self, ev: FlowEvent) -> None:
        if self._bus is not None:
            await self._bus.publish(ev)

    def rtp_target(self, port: int) -> tuple[str, int]:
        return (self._cfg.rtp_host, port)
