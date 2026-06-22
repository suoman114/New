"""scenario 테스트 — 로더, 기대값, MCPTT 타임라인 엔드투엔드(네트워크 없이)."""

from pathlib import Path

from sim.platform.config import find_config_path
from sim.platform.eventbus import EventBus
from sim.rtp import RtpPacket
from sim.scenario import (
    ScenarioEngine,
    build_expectations,
    load_all,
    load_scenario,
    mdn_digits,
)
from sim.scenario.loader import Scenario


def _scenarios_dir() -> Path:
    return find_config_path().parent / "scenarios"


class CollectingFeeder:
    """네트워크 없이 송신을 수집하는 테스트용 Feeder."""

    def __init__(self) -> None:
        self.sip: list[bytes] = []
        self.rtp: list[tuple[int, RtpPacket]] = []

    async def send_sip(self, data, *, event=None, session_id="", call_id="", label="SIP"):
        self.sip.append(data)

    async def send_rtp(self, packet, port, *, session_id="", call_id=""):
        self.rtp.append((port, packet))


def test_mdn_digits_strips_country_code():
    assert mdn_digits("tel:+82585102802") == "585102802"
    assert mdn_digits("01012345678") == "01012345678"


def test_load_all_scenarios():
    scenarios = load_all(_scenarios_dir())
    assert "MCPTT-GROUP-FLOOR" in scenarios
    assert "IMS-VOICE-INBOUND" in scenarios
    mc = scenarios["MCPTT-GROUP-FLOOR"]
    assert mc.service_type == "MCPTT"
    assert mc.mcptt and mc.mcptt.group_id == "98152020001"
    assert len(mc.floor_sequence) == 3


def test_build_expectations_mcptt():
    sc = load_scenario(_scenarios_dir() / "MCPTT-GROUP-FLOOR.yaml")
    exp = build_expectations(sc, session_id="s1", call_id="call-xyz")
    assert len(exp.talk_spurts) == 3
    # 3번째 floor 는 duration 0 → 빈 발언("No packets recorded")
    assert exp.talk_spurts[2].expect_empty is True
    assert exp.talk_spurts[0].frame_count == 200  # 4초 → 200 frame
    # RMQ floor 시퀀스 TAKEN/IDLE × 3
    assert exp.rmq_change_sequence == ["TAKEN", "IDLE"] * 3
    # 파일명 정규식이 실 파일명과 매칭
    import re
    real = "M_tb2bua-tpf_cfua_recorder1_-11401_opf_ob2bua-abcd_585102802_98152020001_20260620000036_5008.awb"
    assert re.match(exp.talk_spurts[0].name_regex, real)


async def test_engine_runs_mcptt_end_to_end():
    sc = load_scenario(_scenarios_dir() / "MCPTT-GROUP-FLOOR.yaml")
    bus = EventBus()
    feeder = CollectingFeeder()
    engine = ScenarioEngine(feeder, bus=bus, realtime=False)

    result = await engine.run(sc, session_id="sess-1")

    # 3개 talk spurt, INVITE+ACK+BYE = 3 SIP
    assert len(result.spurts) == 3
    assert result.sip_count == 3
    assert len(feeder.sip) == 3

    # 발언 1(4초=200frame), 발언 2(6초=300frame), 발언 3(0초=0frame)
    assert result.spurts[0].sent_packets == 200
    assert result.spurts[1].sent_packets == 300
    assert result.spurts[2].sent_packets == 0
    assert feeder.rtp and len(feeder.rtp) == 500

    # 각 spurt 는 서로 다른 RTP 포트를 할당받고 회수 → 동시 사용 0
    used_ports = {p for p, _ in feeder.rtp}
    assert len(used_ports) >= 2

    # ladder: floor TAKEN/IDLE(RMQ), RTP 요약, SYS start/done 이벤트가 발행됨
    rmq = bus.recent(channel="RMQ", limit=100)
    labels = [e.label for e in rmq]
    assert labels.count("floor TAKEN") == 3
    assert labels.count("floor IDLE") == 3
    assert len(bus.recent(channel="RTP", limit=100)) == 3
    assert len(bus.recent(channel="SYS", limit=100)) >= 2


async def test_engine_rtp_packets_are_valid_and_correlated():
    sc = load_scenario(_scenarios_dir() / "MCPTT-GROUP-FLOOR.yaml")
    feeder = CollectingFeeder()
    engine = ScenarioEngine(feeder, realtime=False)
    result = await engine.run(sc, session_id="sess-2")

    # 첫 발언의 패킷들은 단일 SSRC + 연속 seq
    first_ssrc = result.spurts[0].ssrc
    port0 = result.spurts[0].rtp_port
    pkts = [pkt for p, pkt in feeder.rtp if p == port0]
    assert all(pkt.ssrc == first_ssrc for pkt in pkts)
    seqs = [pkt.sequence for pkt in pkts]
    assert seqs == sorted(seqs)
    # 통계 일관성
    st = result.spurts[0].stats
    assert st.total_packets == 200 and st.play_time_ms == 4000


async def test_engine_packet_loss_creates_drops():
    sc = load_scenario(_scenarios_dir() / "MCPTT-GROUP-FLOOR.yaml")
    sc = Scenario.model_validate({**sc.model_dump(), "impair": {"packet_loss_pct": 50.0}})
    feeder = CollectingFeeder()
    engine = ScenarioEngine(feeder, realtime=False)
    result = await engine.run(sc, session_id="sess-3")
    # 손실이 발생해 송신 패킷 < frame 수
    assert result.spurts[0].dropped > 0
    assert result.spurts[0].sent_packets < 200
