"""pcap_mirror 주입 — scapy L3 패킷이 실제로 인터페이스(lo)에 주입되는지 캡처 검증.

scapy 미설치 또는 비루트 시 skip.
"""

import asyncio
import os

import pytest

from sim.platform.config import TapperConfig
from sim.rtp import AmrWbStream, RtpPacket, encoder
from sim.tapper import PcapFeeder, scapy_available

pcap_gate = pytest.mark.skipif(
    not scapy_available() or os.geteuid() != 0,
    reason="scapy 미설치 또는 비루트(raw socket 불가)")


def test_pcap_feeder_builds_ip_udp():
    if not scapy_available():
        pytest.skip("scapy 미설치")
    from scapy.all import IP, UDP, Raw
    cfg = TapperConfig(sip_host="127.0.0.1", sip_port=10000)
    f = PcapFeeder(cfg, iface="lo", src_ip="1.2.3.4")
    pkt = f._build(b"hello", "127.0.0.1", 10000)
    assert pkt[IP].src == "1.2.3.4" and pkt[IP].dst == "127.0.0.1"
    assert pkt[UDP].dport == 10000 and bytes(pkt[Raw].load) == b"hello"


@pcap_gate
async def test_pcap_inject_captured_on_loopback():
    from scapy.all import AsyncSniffer, Raw

    marker = b"INVITE sip:pcap-test SIP/2.0\r\n\r\n"
    sip_port, rtp_port = 18000, 18001
    sniffer = AsyncSniffer(iface="lo", store=True)
    sniffer.start()
    await asyncio.sleep(0.4)

    cfg = TapperConfig(sip_host="127.0.0.1", sip_port=sip_port,
                       rtp_host="127.0.0.1", rtp_port_base=rtp_port, rtp_port_count=1)
    feeder = PcapFeeder(cfg, iface="lo", src_ip="127.0.0.1")
    await feeder.start()
    rtp_pkt = AmrWbStream(ssrc=7, start_seq=3).build(encoder.speech_frames(1, ft=8))[0]
    try:
        await feeder.send_sip(marker)
        await feeder.send_rtp(rtp_pkt, rtp_port)
        await asyncio.sleep(0.6)
    finally:
        await feeder.close()
    await asyncio.sleep(0.2)
    sniffer.stop()
    pkts = sniffer.results

    raws = [bytes(p[Raw].load) for p in pkts if p.haslayer(Raw)]
    assert feeder.sent_sip == 1 and feeder.sent_rtp == 1
    # 주입한 SIP 마커가 와이어에서 캡처됨
    assert any(marker in r for r in raws), f"SIP not captured ({len(raws)} raw pkts)"
    # 주입한 RTP 가 캡처되어 유효 RTP 로 파싱됨
    rtp_raw = [r for r in raws if r == rtp_pkt.pack()]
    assert rtp_raw, "RTP not captured"
    back = RtpPacket.unpack(rtp_raw[0])
    assert back.ssrc == 7 and back.sequence == 3
