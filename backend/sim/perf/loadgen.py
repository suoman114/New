"""부하 생성기: 동시 세션 ramp-up.

scenario 엔진을 재사용해 N 세션을 CPS(call-per-second) 속도로 점증 구동하고 메트릭을 수집한다.
실제 실행은 주입된 `runner` 에 위임하므로(중복 구현 금지) 네트워크 없이도 테스트 가능하다.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from ..platform.eventbus import EventBus
from ..platform.models import _now_ms
from ..scenario.engine import ScenarioEngine
from ..scenario.loader import Scenario
from ..tapper.port_alloc import RtpPortAllocator
from ..tapper.udp_sender import TapperFeeder
from .metrics import PerfReport, PerfSample

Runner = Callable[[Scenario, str], Awaitable]


@dataclass
class LoadSpec:
    total: int = 10                  # 총 세션 수
    cps: float = 5.0                 # 초당 세션 생성률(ramp)
    realtime: bool = False           # RTP 20ms 페이싱 여부


def make_default_runner(*, feeder_factory: Callable[[], object],
                        port_alloc: RtpPortAllocator,
                        bus: Optional[EventBus] = None, realtime: bool = False) -> Runner:
    """ScenarioEngine 기반 기본 runner. feeder_factory 로 세션별 송신기를 만든다."""

    async def runner(scenario: Scenario, session_id: str):
        feeder = feeder_factory()
        started = False
        try:
            if isinstance(feeder, TapperFeeder):
                await feeder.start()
                started = True
            engine = ScenarioEngine(feeder, bus=bus, port_alloc=port_alloc,
                                    realtime=realtime)
            return await engine.run(scenario, session_id=session_id)
        finally:
            if started and isinstance(feeder, TapperFeeder):
                await feeder.close()

    return runner


class LoadGenerator:
    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    async def run(self, scenario: Scenario, spec: LoadSpec) -> PerfReport:
        report = PerfReport(wall_start_ms=_now_ms())
        interval = 1.0 / spec.cps if spec.cps > 0 else 0.0
        tasks: list[asyncio.Task] = []

        for _ in range(max(1, spec.total)):
            sid = uuid.uuid4().hex[:12]
            sample = PerfSample(session_id=sid, launch_ms=_now_ms())
            report.samples.append(sample)
            tasks.append(asyncio.create_task(self._run_one(scenario, sid, sample)))
            if interval:
                await asyncio.sleep(interval)   # ramp 간격

        await asyncio.gather(*tasks, return_exceptions=True)
        report.wall_end_ms = _now_ms()
        return report

    async def _run_one(self, scenario: Scenario, sid: str, sample: PerfSample) -> None:
        sample.start_ms = _now_ms()
        try:
            result = await self._runner(scenario, sid)
            sample.ok = True
            sample.sip = getattr(result, "sip_count", 0)
            sample.packets = sum(sp.sent_packets for sp in getattr(result, "spurts", []))
        except Exception as exc:  # noqa: BLE001
            sample.ok = False
            sample.error = str(exc)
        finally:
            sample.end_ms = _now_ms()
