"""성능 메트릭 수집/집계.

세션 setup latency, 처리 시간 분포(p50/p95/p99), throughput, 실패율, 송출량.
1차는 기능검증 위주이며 구조는 대규모 확장(동시 ~2000+)을 염두에 둔다(CLAUDE.md §7).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PerfSample:
    session_id: str
    launch_ms: float                 # 시작 요청 시각
    start_ms: float = 0.0            # 실제 실행 시작
    end_ms: float = 0.0              # 실행 종료
    ok: bool = False
    packets: int = 0                 # 송출 RTP 패킷
    sip: int = 0                     # 송출 SIP
    error: str = ""

    @property
    def setup_latency_ms(self) -> float:
        """요청→실행시작 지연(스케줄 큐잉)."""
        return max(0.0, self.start_ms - self.launch_ms)

    @property
    def duration_ms(self) -> float:
        return max(0.0, self.end_ms - self.start_ms)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


@dataclass
class PerfReport:
    samples: list[PerfSample] = field(default_factory=list)
    wall_start_ms: float = 0.0
    wall_end_ms: float = 0.0

    @property
    def total(self) -> int:
        return len(self.samples)

    @property
    def success(self) -> int:
        return sum(1 for s in self.samples if s.ok)

    @property
    def failed(self) -> int:
        return self.total - self.success

    @property
    def failure_rate(self) -> float:
        return (self.failed / self.total) if self.total else 0.0

    def durations(self) -> list[float]:
        return [s.duration_ms for s in self.samples if s.ok]

    def setup_latencies(self) -> list[float]:
        return [s.setup_latency_ms for s in self.samples]

    def total_packets(self) -> int:
        return sum(s.packets for s in self.samples)

    def throughput_sps(self) -> float:
        wall = (self.wall_end_ms - self.wall_start_ms) / 1000.0
        return (self.success / wall) if wall > 0 else 0.0

    def summary(self) -> dict:
        durs = self.durations()
        lats = self.setup_latencies()
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "failure_rate": round(self.failure_rate, 4),
            "throughput_sps": round(self.throughput_sps(), 3),
            "duration_ms": {
                "p50": round(_percentile(durs, 50), 2),
                "p95": round(_percentile(durs, 95), 2),
                "p99": round(_percentile(durs, 99), 2),
            },
            "setup_latency_ms": {
                "p50": round(_percentile(lats, 50), 2),
                "p95": round(_percentile(lats, 95), 2),
            },
            "total_packets": self.total_packets(),
            "wall_ms": round(self.wall_end_ms - self.wall_start_ms, 2),
        }
