"""dashboard-backend 앱 상태/오케스트레이션.

EventBus·LogStore·시나리오 레지스트리·실행 세션·검증 결과를 보유하고,
시나리오 실행(run/stop)을 관리한다. 비즈니스 로직은 엔진에 위임하고 여기서는 조립만 한다.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Callable, Optional

from sim.platform.config import DbConfig, SimConfig, load_config
from sim.platform.db import RecordInfoRepository, make_repository
from sim.platform.eventbus import EventBus
from sim.platform.logging import default_store
from sim.platform.models import SessionInfo, ValidationResult
from sim.rmq import RmqMonitor
from sim.scenario import ScenarioEngine, RunResult, load_all
from sim.scenario.engine import Feeder
from sim.perf import LoadGenerator, LoadSpec, make_default_runner, perf_flow_event
from sim.tapper.port_alloc import RtpPortAllocator
from sim.tapper.udp_sender import TapperFeeder
from sim.validator import Validator

_UNSET = object()


class AppState:
    def __init__(self, config: Optional[SimConfig] = None,
                 feeder_factory: Optional[Callable[[], Feeder]] = None,
                 repo_factory: Optional[Callable[[DbConfig], RecordInfoRepository]] = None
                 ) -> None:
        self.config = config or load_config()
        self.bus = EventBus(ring_size=self.config.sim.event_ring_size)
        self.logs = default_store
        from sim.platform.config import find_config_path
        self.scenarios = load_all(find_config_path().parent / "scenarios")
        self.sessions: dict[str, SessionInfo] = {}
        self.run_results: dict[str, RunResult] = {}
        self.results: dict[str, ValidationResult] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._feeder_factory = feeder_factory
        self.last_perf: dict | None = None
        # 실 서버 통합: DB repo(지연 생성) + RMQ shadow monitor
        self._repo_factory = repo_factory or make_repository
        self._repo: object = _UNSET
        self.rmq = RmqMonitor(self.config.rmq, bus=self.bus)

    def _make_feeder(self) -> Feeder:
        if self._feeder_factory:
            return self._feeder_factory()
        return TapperFeeder(self.config.tapper, bus=self.bus)

    async def run_scenario(self, scenario_id: str, *, session_count: int = 1,
                           realtime: bool = False, wait: bool = False) -> list[str]:
        if scenario_id not in self.scenarios:
            raise KeyError(scenario_id)
        session_ids: list[str] = []
        for _ in range(max(1, session_count)):
            sid = uuid.uuid4().hex[:12]
            session_ids.append(sid)
            self.sessions[sid] = SessionInfo(session_id=sid, scenario_id=scenario_id,
                                             service_type=self.scenarios[scenario_id].service_type,
                                             state="RUNNING")
            task = asyncio.create_task(self._run_one(sid, scenario_id, realtime))
            self._tasks[sid] = task
        if wait:
            await asyncio.gather(*[self._tasks[s] for s in session_ids],
                                 return_exceptions=True)
        return session_ids

    async def _run_one(self, session_id: str, scenario_id: str, realtime: bool) -> None:
        scenario = self.scenarios[scenario_id]
        feeder = self._make_feeder()
        started = False
        try:
            if isinstance(feeder, TapperFeeder):
                await feeder.start()
                started = True
            ports = RtpPortAllocator(self.config.tapper.rtp_port_base,
                                     self.config.tapper.rtp_port_count)
            engine = ScenarioEngine(feeder, bus=self.bus, port_alloc=ports,
                                    realtime=realtime)
            result = await engine.run(scenario, session_id=session_id)
            self.run_results[session_id] = result
            info = self.sessions[session_id]
            info.call_id = result.call_id
            info.state = "DONE"
            info.summary = f"spurts={len(result.spurts)} sip={result.sip_count}"
            from sim.platform.models import _now_ms
            info.ended_ms = _now_ms()
        except asyncio.CancelledError:
            self.sessions[session_id].state = "ERROR"
            self.sessions[session_id].summary = "취소됨"
            raise
        except Exception as exc:  # noqa: BLE001
            self.sessions[session_id].state = "ERROR"
            self.sessions[session_id].summary = f"error: {exc}"
        finally:
            if started and isinstance(feeder, TapperFeeder):
                await feeder.close()

    async def run_load(self, scenario_id: str, *, total: int = 10, cps: float = 5.0,
                       realtime: bool = False) -> dict:
        """부하 시험: scenario 엔진을 N 세션 ramp-up 구동하고 요약을 반환."""
        if scenario_id not in self.scenarios:
            raise KeyError(scenario_id)
        ports = RtpPortAllocator(self.config.tapper.rtp_port_base,
                                 self.config.tapper.rtp_port_count)
        runner = make_default_runner(feeder_factory=self._make_feeder, port_alloc=ports,
                                     bus=self.bus, realtime=realtime)
        gen = LoadGenerator(runner)
        report = await gen.run(self.scenarios[scenario_id],
                               LoadSpec(total=total, cps=cps, realtime=realtime))
        await self.bus.publish(perf_flow_event(report, scenario_id=scenario_id))
        self.last_perf = report.summary()
        return self.last_perf

    async def stop_session(self, session_id: str) -> bool:
        task = self._tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def metrics(self) -> dict:
        states: dict[str, int] = {}
        for s in self.sessions.values():
            states[s.state] = states.get(s.state, 0) + 1
        return {
            "sessions_total": len(self.sessions),
            "by_state": states,
            "events_buffered": len(self.bus.recent(limit=10**9)),
            "ws_subscribers": self.bus.subscriber_count,
        }

    # ── 실 서버 통합 ─────────────────────────────────────────────────────────
    async def start_rmq(self) -> bool:
        """RMQ shadow monitor 시작(graceful degrade)."""
        return await self.rmq.start()

    def _get_repo(self) -> Optional[RecordInfoRepository]:
        """DB repository 지연 생성(실패 시 None, 통합 비활성)."""
        if self._repo is _UNSET:
            try:
                self._repo = self._repo_factory(self.config.sut.db)
            except Exception:  # noqa: BLE001
                self._repo = None
        return self._repo  # type: ignore[return-value]

    def _fs_root(self) -> Optional[str]:
        """녹취 파일 루트(램디스크 우선, 없으면 NAS). 둘 다 없으면 None."""
        for p in (self.config.sut.rec_ramdisk, self.config.sut.rec_nas):
            if p and os.path.isdir(os.path.expanduser(p)):
                return os.path.expanduser(p)
        return None

    async def validate_session(self, session_id: str) -> ValidationResult:
        """실행 결과를 실 SUT 산출물(DB/파일) + RMQ 관찰과 대조하여 검증."""
        run = self.run_results.get(session_id)
        if run is None:
            raise KeyError(session_id)
        repo = self._get_repo()
        # DB 연결 가능 여부 확인(불가 시 DB 검증 스킵)
        if repo is not None and not self._db_ok(repo):
            repo = None
        validator = Validator(repo=repo, fs_root=self._fs_root(), bus=self.bus,
                              mode_set_max=8)
        result = await validator.validate(run.expectations, run.spurts)
        # RMQ floor/시퀀스 검증(모니터가 해당 호 메시지를 관찰한 경우에만)
        if self.rmq.enabled and run.call_id in self.rmq.trackers:
            for item in self.rmq.trackers[run.call_id].validate(run.expectations):
                result.add(item)
        self.results[session_id] = result
        info = self.sessions.get(session_id)
        if info is not None:
            info.validation_passed = result.passed
            info.state = "DONE"
        return result

    @staticmethod
    def _db_ok(repo: RecordInfoRepository) -> bool:
        try:
            repo.by_call_id("__healthcheck__")
            return True
        except Exception:  # noqa: BLE001
            return False

    def integration_health(self) -> dict:
        repo = self._get_repo()
        db_ok = repo is not None and self._db_ok(repo)
        return {
            "db": {"reachable": db_ok, "table": self.config.sut.db.table,
                   "host": self.config.sut.db.host, "database": self.config.sut.db.database},
            "rmq": {"enabled": self.rmq.enabled, "host": self.config.rmq.host,
                    "tracked_calls": len(self.rmq.trackers)},
            "fs": {"active_root": self._fs_root(),
                   "ramdisk": os.path.isdir(os.path.expanduser(self.config.sut.rec_ramdisk)),
                   "nas": os.path.isdir(os.path.expanduser(self.config.sut.rec_nas))},
            "inject_mode": self.config.inject_mode,
        }
