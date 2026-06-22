"""dashboard-backend 앱 상태/오케스트레이션.

EventBus·LogStore·시나리오 레지스트리·실행 세션·검증 결과를 보유하고,
시나리오 실행(run/stop)을 관리한다. 비즈니스 로직은 엔진에 위임하고 여기서는 조립만 한다.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Callable, Optional

from sim.platform.config import SimConfig, load_config
from sim.platform.eventbus import EventBus
from sim.platform.logging import default_store
from sim.platform.models import SessionInfo, ValidationResult
from sim.scenario import ScenarioEngine, RunResult, load_all
from sim.scenario.engine import Feeder
from sim.tapper.port_alloc import RtpPortAllocator
from sim.tapper.udp_sender import TapperFeeder


class AppState:
    def __init__(self, config: Optional[SimConfig] = None,
                 feeder_factory: Optional[Callable[[], Feeder]] = None) -> None:
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
