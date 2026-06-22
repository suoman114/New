"""시나리오 타임라인 엔진.

호별 상태머신으로 sip-engine / rtp-media / tapper-feed 를 구동한다.
1차 우선 구현: MCPTT 그룹콜 + floor(TAKEN/IDLE) talk-spurt 녹취(observed-from-logs.md §8).

엔진은 네트워크 없이도 테스트 가능하도록 `Feeder` Protocol 에 의존한다(TapperFeeder = 실 송신,
CollectingFeeder = 테스트). 모든 단계를 EventBus 로 발행하여 ladder/로그 드릴다운을 채운다.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from ..platform.eventbus import EventBus
from ..platform.logging import log_for
from ..platform.models import FlowEvent
from ..rtp import AmrWbStream, encoder, impair, rtp_stat_event
from ..rtp.amrwb import AmrFrame, parse_oa
from ..rtp.sender import StreamStats
from ..sip import amrwb_offer, build_sdp, sip_flow_event
from ..sip.ua import CallerUA
from ..tapper.port_alloc import RtpPortAllocator
from .expectations import ScenarioExpectations, build_expectations
from .loader import Scenario

MCPTT_DOMAIN = "ptt.humetro.mnc031.mcc450.3gppnetwork.org"
IMS_DOMAIN = "ims.humetro.mnc031.mcc450.3gppnetwork.org"


@runtime_checkable
class Feeder(Protocol):
    async def send_sip(self, data: bytes, *, event: Optional[FlowEvent] = None,
                       session_id: str = "", call_id: str = "", label: str = "SIP") -> None: ...

    async def send_rtp(self, packet, port: int, *, session_id: str = "",
                       call_id: str = "") -> None: ...


@dataclass
class SpurtResult:
    index: int
    talker_mdn: str
    rtp_port: int
    ssrc: int
    sent_packets: int
    dropped: int
    stats: StreamStats
    # 실제 송신된 frame(손실 반영) — validator 골든 재구성용
    frames: list[AmrFrame] = field(default_factory=list)


@dataclass
class RunResult:
    session_id: str
    call_id: str
    scenario_id: str
    service_type: str
    expectations: ScenarioExpectations
    spurts: list[SpurtResult] = field(default_factory=list)
    sip_count: int = 0
    events: int = 0


def _mcptt_call_id() -> str:
    n = random.randint(10000, 99999)
    return f"tb2bua-tpf_cfua_recorder1_-{n}_opf_ob2bua-{uuid.uuid4().hex}"


def _ims_call_id() -> str:
    # 실 로그 형태: 1339172425_809000108@104.240.17.77
    return f"{random.randint(10**9, 10**10)}_{random.randint(10**8, 10**9)}@104.240.17.77"


class ScenarioEngine:
    def __init__(self, feeder: Feeder, *, bus: Optional[EventBus] = None,
                 port_alloc: Optional[RtpPortAllocator] = None,
                 realtime: bool = True, time_scale: float = 1.0) -> None:
        self._feeder = feeder
        self._bus = bus
        self._ports = port_alloc or RtpPortAllocator()
        self._realtime = realtime
        self._time_scale = time_scale
        self._event_count = 0

    async def _emit(self, ev: FlowEvent, *, log: str = "") -> FlowEvent:
        self._event_count += 1
        if log:
            log_for(ev, log)
        if self._bus is not None:
            await self._bus.publish(ev)
        return ev

    async def run(self, scenario: Scenario, *, session_id: Optional[str] = None) -> RunResult:
        session_id = session_id or uuid.uuid4().hex[:12]
        if scenario.service_type == "MCPTT":
            return await self._run_mcptt(scenario, session_id)
        if scenario.service_type == "IMS":
            return await self._run_ims(scenario, session_id)
        raise NotImplementedError(f"service_type={scenario.service_type} 미구현")

    # ── MCPTT 그룹콜 타임라인 ────────────────────────────────────────────────
    async def _run_mcptt(self, scenario: Scenario, session_id: str) -> RunResult:
        call_id = _mcptt_call_id()
        exp = build_expectations(scenario, session_id=session_id, call_id=call_id)
        result = RunResult(session_id=session_id, call_id=call_id, scenario_id=scenario.id,
                           service_type="MCPTT", expectations=exp)

        await self._emit(FlowEvent(
            session_id=session_id, call_id=call_id, channel="SYS", direction="SIM-INTERNAL",
            peer="scenario", label="scenario start",
            summary=f"{scenario.id} group={scenario.mcptt.group_id if scenario.mcptt else '-'}"),
            log=f"start MCPTT scenario {scenario.id}")

        # 1) 그룹콜 셋업(INVITE → ACK). Tapper 가 미러링한 SIP 를 VCSM 으로 주입.
        members = [m.get("mdn", "") for m in (scenario.mcptt.members if scenario.mcptt else [])]
        caller = members[0] if members else "tel:+82585102802"
        from_uri = f"<sip:{caller}@{MCPTT_DOMAIN}>"
        to_uri = f"<sip:{scenario.mcptt.group_id if scenario.mcptt else 'group'}@{MCPTT_DOMAIN}>"
        ua = CallerUA(from_uri=from_uri, to_uri=to_uri, via_host="111.252.2.49",
                      via_port=5080, call_id=call_id)
        offer = build_sdp(amrwb_offer("111.252.2.49", 50020, pt=scenario.media.pt,
                                      mode_set=max(scenario.media.mode_set)))
        await self._send_sip(ua.invite(sdp=offer), session_id, call_id, "VCSM")
        await self._send_sip(ua.ack(), session_id, call_id, "VCSM")
        result.sip_count += 2

        # 2) floor 시퀀스: 각 talk spurt = 파일 1개(FILE_INDEX 증가)
        ft = max(scenario.media.mode_set)
        for spurt_exp in exp.talk_spurts:
            sr = await self._stream_media(scenario, session_id, call_id, spurt_exp, ft,
                                          emit_floor=True)
            result.spurts.append(sr)

        # 3) 종료(BYE)
        await self._send_sip(ua.bye(), session_id, call_id, "VCSM")
        result.sip_count += 1

        await self._emit(FlowEvent(
            session_id=session_id, call_id=call_id, channel="SYS", direction="SIM-INTERNAL",
            peer="scenario", label="scenario done",
            summary=f"spurts={len(result.spurts)} sip={result.sip_count}"))

        result.events = self._event_count
        return result

    # ── IMS 음성 타임라인 (caller/callee 분리 녹취) ────────────────────────────
    async def _run_ims(self, scenario: Scenario, session_id: str) -> RunResult:
        call_id = _ims_call_id()
        exp = build_expectations(scenario, session_id=session_id, call_id=call_id)
        result = RunResult(session_id=session_id, call_id=call_id, scenario_id=scenario.id,
                           service_type="IMS", expectations=exp)
        call = scenario.call
        from_no = call.from_no if call else ""
        to_no = call.to_no if call else ""

        await self._emit(FlowEvent(
            session_id=session_id, call_id=call_id, channel="SYS", direction="SIM-INTERNAL",
            peer="scenario", label="scenario start",
            summary=f"{scenario.id} {from_no}→{to_no} outbound={call.outbound if call else '-'}"),
            log=f"start IMS scenario {scenario.id}")

        # 1) 호 셋업 (INVITE → ACK)
        ua = CallerUA(from_uri=f"<sip:{from_no}@{IMS_DOMAIN}>",
                      to_uri=f"<tel:{to_no};phone-context={IMS_DOMAIN}>",
                      via_host="104.250.1.60", via_port=5060, call_id=call_id)
        offer = build_sdp(amrwb_offer("104.240.17.77", 50020, pt=scenario.media.pt,
                                      mode_set=max(scenario.media.mode_set)))
        await self._send_sip(ua.invite(sdp=offer), session_id, call_id, "VCSM")
        await self._send_sip(ua.ack(), session_id, call_id, "VCSM")
        result.sip_count += 2

        # 2) recording_start (VCSM→VCMM): caller/callee 양 레그 파일 시작
        await self._emit(FlowEvent(
            session_id=session_id, call_id=call_id, channel="RMQ", direction="SUT-INTERNAL",
            peer="VCSM", label="recording_start_req",
            summary=f"caller/callee 분리 녹취 {from_no}/{to_no}",
            payload={"type": "recording_start_req", "from_no": from_no, "to_no": to_no,
                     "service_type": "IMS"}),
            log="recording_start_req (IMS)")

        # 3) 양 레그 미디어 송출
        ft = max(scenario.media.mode_set)
        for spurt_exp in exp.talk_spurts:
            sr = await self._stream_media(scenario, session_id, call_id, spurt_exp, ft,
                                          emit_floor=False)
            result.spurts.append(sr)

        # 4) recording_stop + BYE
        await self._emit(FlowEvent(
            session_id=session_id, call_id=call_id, channel="RMQ", direction="SUT-INTERNAL",
            peer="VCSM", label="recording_stop_req",
            summary=f"{from_no}/{to_no} 종료",
            payload={"type": "recording_stop_req", "from_no": from_no, "to_no": to_no}))
        await self._send_sip(ua.bye(), session_id, call_id, "VCSM")
        result.sip_count += 1

        await self._emit(FlowEvent(
            session_id=session_id, call_id=call_id, channel="SYS", direction="SIM-INTERNAL",
            peer="scenario", label="scenario done",
            summary=f"legs={len(result.spurts)} sip={result.sip_count}"))
        result.events = self._event_count
        return result

    async def _stream_media(self, scenario: Scenario, session_id: str, call_id: str,
                            spurt_exp, ft: int, *, emit_floor: bool) -> SpurtResult:
        if emit_floor:
            # floor TAKEN: 서버측은 recording_change(TAKEN)로 새 파일 시작.
            await self._emit(FlowEvent(
                session_id=session_id, call_id=call_id, channel="RMQ",
                direction="SUT-INTERNAL", peer="VCMM_0", label="floor TAKEN",
                summary=f"talker={spurt_exp.talker_mdn} (expect new file idx+{spurt_exp.index})",
                payload={"type": "TAKEN", "caller_mdn": spurt_exp.talker_mdn,
                         "audio_extension": "awb"}),
                log=f"floor TAKEN by {spurt_exp.talker_mdn}")

        port = self._ports.allocate()
        ssrc = random.getrandbits(32)
        frames = encoder.talk_spurt(spurt_exp.duration_ms, ft=ft)
        if scenario.impair.inject_silence and frames:
            frames = impair.inject_silence(frames, every=10, run=1)
        stream = AmrWbStream(ssrc=ssrc, payload_type=scenario.media.pt,
                             start_seq=random.randint(0, 1000),
                             start_ts=random.randint(0, 100000))
        packets = stream.build(frames)
        packets, dropped = impair.drop_random(packets, scenario.impair.packet_loss_pct,
                                              seed=spurt_exp.index)

        for pkt in packets:
            await self._feeder.send_rtp(pkt, port, session_id=session_id, call_id=call_id)
            if self._realtime:
                await asyncio.sleep(0.02 * self._time_scale)

        stats = stream.stats(packets)
        await self._emit(rtp_stat_event(stats, session_id=session_id, call_id=call_id,
                                        dropped=len(dropped)),
                         log=(f"sent {len(packets)} RTP pkts on port {port} "
                              f"(empty={spurt_exp.expect_empty})"))

        if emit_floor:
            # floor IDLE: 서버측은 파일 종료(FILE_STATUS 2).
            await self._emit(FlowEvent(
                session_id=session_id, call_id=call_id, channel="RMQ",
                direction="SUT-INTERNAL", peer="VCMM_0", label="floor IDLE",
                summary=f"talker={spurt_exp.talker_mdn} end",
                payload={"type": "IDLE"}))
        self._ports.release(port)

        # 실제 송신된 패킷의 frame 복원(손실 반영) — 골든 재구성 입력
        sent_frames = [parse_oa(p.payload)[0] for p in packets if parse_oa(p.payload)]

        return SpurtResult(index=spurt_exp.index, talker_mdn=spurt_exp.talker_mdn,
                           rtp_port=port, ssrc=ssrc, sent_packets=len(packets),
                           dropped=len(dropped), stats=stats, frames=sent_frames)

    async def _send_sip(self, msg, session_id: str, call_id: str, peer: str) -> None:
        ev = sip_flow_event(msg, session_id=session_id, direction="SIM->SUT",
                            peer=peer, call_id=call_id)
        await self._feeder.send_sip(msg.serialize(), event=ev, session_id=session_id,
                                    call_id=call_id, label=ev.label)
        self._event_count += 1
        if self._bus is not None:
            log_for(ev, f"SIP {ev.label} → {peer}")
