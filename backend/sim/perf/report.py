"""성능 결과 → FlowEvent(channel=SYS) 발행 (대시보드 성능 패널/SYS 집계)."""

from __future__ import annotations

from ..platform.models import FlowEvent
from .metrics import PerfReport


def perf_flow_event(report: PerfReport, *, session_id: str = "perf",
                    scenario_id: str = "") -> FlowEvent:
    s = report.summary()
    sev = "info" if report.failure_rate == 0 else "warn"
    return FlowEvent(
        session_id=session_id, channel="SYS", direction="SIM-INTERNAL", peer="perf",
        label="perf result", severity=sev,
        summary=(f"{scenario_id} total={s['total']} ok={s['success']} "
                 f"fail={s['failed']} thr={s['throughput_sps']}sps "
                 f"dur_p95={s['duration_ms']['p95']}ms pkts={s['total_packets']}"),
        payload=s,
    )
