#!/usr/bin/env python3
"""엔드투엔드 데모: 시나리오를 로드해 SIP+RTP 를 Tapper UDP 로 주입하고 ladder 를 출력.

사용:
    cd backend
    python run_demo.py                         # MCPTT-GROUP-FLOOR, 빠른 모드
    python run_demo.py --scenario MCPTT-GROUP-FLOOR --realtime
    python run_demo.py --time-scale 0.05       # 실시간이되 20배속

주의: inject_mode=tapper_udp 기준으로 config/sim.yaml 의 VCSM/VCMM 포트로 실제 UDP 를 송신한다.
실 서버가 없으면 패킷은 버려지지만(데모), 파이프라인/ladder 는 동일하게 동작한다.
"""

from __future__ import annotations

import argparse
import asyncio

from sim.platform.config import load_config, find_config_path
from sim.platform.eventbus import EventBus
from sim.platform.logging import configure_logging, default_store
from sim.scenario import ScenarioEngine, load_all
from sim.tapper.port_alloc import RtpPortAllocator
from sim.tapper.udp_sender import TapperFeeder


async def _print_ladder(bus: EventBus, stop: asyncio.Event) -> None:
    cols = {"UA-Caller": 0, "VCTP": 1, "VCSM": 2, "VCMM_0": 3, "VCMC": 4, "scenario": 5}
    async for ev in bus.subscribe():
        col = cols.get(ev.peer, 5)
        indent = "    " * col
        sev = {"info": "", "warn": "⚠ ", "error": "✗ "}.get(ev.severity, "")
        print(f"[{ev.channel:<10}] {indent}{sev}{ev.label}  | {ev.summary}")
        if stop.is_set():
            break


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="MCPTT-GROUP-FLOOR")
    ap.add_argument("--realtime", action="store_true", help="실시간 20ms 페이싱")
    ap.add_argument("--time-scale", type=float, default=1.0, help="실시간 배속(작을수록 빠름)")
    args = ap.parse_args()

    configure_logging()
    cfg = load_config()
    scenarios = load_all(find_config_path().parent / "scenarios")
    scenario = scenarios[args.scenario]

    bus = EventBus(ring_size=cfg.sim.event_ring_size)
    stop = asyncio.Event()
    printer = asyncio.create_task(_print_ladder(bus, stop))

    feeder = TapperFeeder(cfg.tapper, bus=bus)
    await feeder.start()
    ports = RtpPortAllocator(cfg.tapper.rtp_port_base, cfg.tapper.rtp_port_count)
    engine = ScenarioEngine(feeder, bus=bus, port_alloc=ports,
                            realtime=args.realtime, time_scale=args.time_scale)

    print(f"\n=== RUN {scenario.id} (inject_mode={cfg.inject_mode}, "
          f"SIP→{cfg.tapper.sip_host}:{cfg.tapper.sip_port}, "
          f"RTP→{cfg.tapper.rtp_host}:{cfg.tapper.rtp_port_base}+) ===\n")
    result = await engine.run(scenario)
    await asyncio.sleep(0.1)
    stop.set()
    printer.cancel()
    await feeder.close()

    print("\n=== RESULT ===")
    print(f"session={result.session_id} call_id={result.call_id}")
    print(f"SIP sent={result.sip_count}, talk-spurts={len(result.spurts)}, "
          f"events={result.events}, sip_udp={feeder.sent_sip}, rtp_udp={feeder.sent_rtp}")
    for sr in result.spurts:
        print(f"  spurt#{sr.index} talker={sr.talker_mdn} port={sr.rtp_port} "
              f"ssrc={sr.ssrc} pkts={sr.sent_packets} drop={sr.dropped} "
              f"play={sr.stats.play_time_ms}ms")

    print("\n=== EXPECTATIONS (validator 입력) ===")
    for ts in result.expectations.talk_spurts:
        kind = "EMPTY(No packets)" if ts.expect_empty else f"{ts.frame_count} frames"
        print(f"  #{ts.index} {ts.talker_mdn} ({ts.talker_digits}) {kind}")
        print(f"       file~ {ts.name_regex}")
    print(f"  RMQ change seq: {result.expectations.rmq_change_sequence}")
    print(f"  FILE_STATUS final = {result.expectations.file_status_final}")

    # 로그 드릴다운 데모: 첫 SYS 이벤트의 로그
    sys_events = bus.recent(channel="SYS", limit=1)
    if sys_events:
        lines = default_store.get(sys_events[0].event_id)
        if lines:
            print(f"\n=== LOG DRILLDOWN (event {sys_events[0].event_id[:8]}) ===")
            for ln in lines:
                print(f"  [{ln.level}] {ln.message}")


if __name__ == "__main__":
    asyncio.run(main())
