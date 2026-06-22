"""tapper-feed 테스트 — 포트 할당, 페이싱, UDP 송신(루프백 수신 검증)."""

import asyncio

import pytest

from sim.platform.config import TapperConfig
from sim.platform.eventbus import EventBus
from sim.rtp import RtpPacket
from sim.rtp.sender import AmrWbStream
from sim.rtp import encoder
from sim.tapper import RtpPortAllocator, pace_fixed
from sim.tapper.udp_sender import TapperFeeder


def test_port_allocator():
    alloc = RtpPortAllocator(base=10001, count=3)
    p1, p2, p3 = alloc.allocate(), alloc.allocate(), alloc.allocate()
    assert {p1, p2, p3} == {10001, 10002, 10003}
    assert alloc.in_use == 3
    with pytest.raises(RuntimeError):
        alloc.allocate()
    alloc.release(p2)
    assert alloc.allocate() == 10002


async def test_pace_fixed_yields_all():
    items = list(range(5))
    out = [x async for x in pace_fixed(items, interval_ms=1)]
    assert out == items


async def test_udp_sender_sip_and_rtp_loopback():
    """루프백 UDP 수신기로 SIP/RTP 송신을 실제 확인."""
    loop = asyncio.get_running_loop()
    received: list[bytes] = []

    class RecvProto(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            received.append(data)

    # 임의 포트로 수신기 바인드
    transport, _ = await loop.create_datagram_endpoint(
        RecvProto, local_addr=("127.0.0.1", 0))
    recv_port = transport.get_extra_info("sockname")[1]

    bus = EventBus()
    cfg = TapperConfig(sip_host="127.0.0.1", sip_port=recv_port,
                       rtp_host="127.0.0.1", rtp_port_base=recv_port, rtp_port_count=1)
    feeder = TapperFeeder(cfg, bus=bus)
    await feeder.start()
    try:
        await feeder.send_sip(b"INVITE sip:x SIP/2.0\r\n\r\n", session_id="s1",
                              call_id="c1", label="INVITE")
        pkt = AmrWbStream(ssrc=1, start_seq=0).build(encoder.speech_frames(1, ft=8))[0]
        await feeder.send_rtp(pkt, recv_port, session_id="s1", call_id="c1")
        await asyncio.sleep(0.05)
    finally:
        await feeder.close()
        transport.close()

    assert feeder.sent_sip == 1 and feeder.sent_rtp == 1
    assert len(received) == 2
    # SIP 송신 이벤트가 EventBus 에 발행됨
    sip_events = bus.recent(channel="SIP")
    assert len(sip_events) == 1 and sip_events[0].peer == "VCSM"


async def test_rtp_packet_received_is_valid_rtp():
    loop = asyncio.get_running_loop()
    received: list[bytes] = []

    class RecvProto(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            received.append(data)

    transport, _ = await loop.create_datagram_endpoint(
        RecvProto, local_addr=("127.0.0.1", 0))
    recv_port = transport.get_extra_info("sockname")[1]
    cfg = TapperConfig(rtp_host="127.0.0.1", rtp_port_base=recv_port, rtp_port_count=1)
    feeder = TapperFeeder(cfg)
    await feeder.start()
    try:
        pkt = AmrWbStream(ssrc=777, start_seq=5, start_ts=320).build(
            encoder.speech_frames(1, ft=8))[0]
        await feeder.send_rtp(pkt, recv_port)
        await asyncio.sleep(0.05)
    finally:
        await feeder.close()
        transport.close()

    assert len(received) == 1
    back = RtpPacket.unpack(received[0])
    assert back.ssrc == 777 and back.sequence == 5 and back.timestamp == 320
