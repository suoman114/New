"""대규모 분산 부하 생성 (~2000+ 확장).

단일 asyncio 루프의 한계를 넘기 위해 **멀티프로세스**로 세션을 분산 생성한다.
각 워커는 독립 asyncio 루프에서 자기 몫의 세션을 구동하고 PerfSample 만 반환한다
(워커는 EventBus 를 공유하지 않으므로 이벤트 폭주가 원천 차단됨 = 이벤트 샘플링).

워커는 picklable 해야 하므로 모듈 레벨 함수/클래스만 사용한다.
실 UDP 주입(TapperFeeder)은 워커별 포트 슬라이스로 가능하나 기본은 NullFeeder(부하 구조 검증).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor

from ..platform.models import _now_ms
from .loadgen import LoadGenerator, LoadSpec, make_default_runner
from .metrics import PerfReport, PerfSample


class NullFeeder:
    """무동작 송신기(분산 워커 기본). 실제 UDP 미발생."""

    async def send_sip(self, data, *, event=None, session_id="", call_id="", label="SIP"):
        pass

    async def send_rtp(self, packet, port, *, session_id="", call_id=""):
        pass


def _worker(payload: dict) -> list[dict]:
    """워커 프로세스 진입점: 자기 몫 세션 구동 → PerfSample dict 리스트."""
    from ..scenario.loader import Scenario
    from ..tapper.port_alloc import RtpPortAllocator

    scenario = Scenario.model_validate(payload["scenario"])
    ports = RtpPortAllocator(payload["rtp_base"], payload["rtp_count"])
    runner = make_default_runner(feeder_factory=NullFeeder, port_alloc=ports,
                                 bus=None, realtime=payload["realtime"])
    gen = LoadGenerator(runner)
    report = asyncio.run(gen.run(scenario, LoadSpec(total=payload["count"],
                                                    cps=payload["cps"],
                                                    realtime=payload["realtime"])))
    return [s.__dict__ for s in report.samples]


class DistributedLoadGenerator:
    def __init__(self, *, rtp_base: int = 10001, rtp_count: int = 1000) -> None:
        self._rtp_base = rtp_base
        self._rtp_count = rtp_count

    async def run(self, scenario, *, total: int, cps: float = 50.0, workers: int = 2,
                  realtime: bool = False) -> PerfReport:
        workers = max(1, min(workers, total))
        base = total // workers
        rem = total % workers
        counts = [base + (1 if i < rem else 0) for i in range(workers)]
        slice_count = max(1, self._rtp_count // workers)
        payloads = [{
            "scenario": scenario.model_dump(),
            "count": c,
            "cps": cps,
            "realtime": realtime,
            "rtp_base": self._rtp_base + i * slice_count,
            "rtp_count": slice_count,
        } for i, c in enumerate(counts) if c > 0]

        report = PerfReport(wall_start_ms=_now_ms())
        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [loop.run_in_executor(ex, _worker, p) for p in payloads]
            results = await asyncio.gather(*futs)
        for rows in results:
            for d in rows:
                report.samples.append(PerfSample(**d))
        report.wall_end_ms = _now_ms()
        return report
