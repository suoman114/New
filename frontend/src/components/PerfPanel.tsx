// 성능/메트릭 패널: 메트릭 폴링 + 채널별 카운트 + 부하 시험(ramp-up) 트리거/요약.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { FlowEvent, Metrics, PerfSummary } from "../api/types";

export function PerfPanel(props: { events: FlowEvent[]; scenarioId: string }) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [perf, setPerf] = useState<PerfSummary | null>(null);
  const [total, setTotal] = useState(20);
  const [workers, setWorkers] = useState(1);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const tick = () => api.metrics().then(setMetrics).catch(() => {});
    tick();
    const t = setInterval(tick, 2000);
    return () => clearInterval(t);
  }, []);

  const runLoad = async () => {
    setBusy(true);
    try {
      setPerf(await api.perfRun(props.scenarioId, total, workers > 1 ? 5000 : 50, workers));
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  };

  const byChannel = props.events.reduce<Record<string, number>>((acc, e) => {
    acc[e.channel] = (acc[e.channel] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="panel perf">
      <div className="panel-head">
        <h3>성능 / 메트릭</h3>
        <div className="row">
          <input
            type="number"
            min={1}
            max={5000}
            value={total}
            onChange={(e) => setTotal(Number(e.target.value))}
            style={{ width: 64 }}
            title="총 세션 수"
          />
          <input
            type="number"
            min={1}
            max={32}
            value={workers}
            onChange={(e) => setWorkers(Number(e.target.value))}
            style={{ width: 48 }}
            title="분산 워커 수(>1: 멀티프로세스)"
          />
          <button onClick={runLoad} disabled={busy || !props.scenarioId}>
            {busy ? "부하 중..." : "⚡ 부하 시험"}
          </button>
        </div>
      </div>

      <div className="metrics">
        <div className="metric">
          <span className="metric-v">{metrics?.sessions_total ?? 0}</span>
          <span className="metric-l">sessions</span>
        </div>
        <div className="metric">
          <span className="metric-v">{metrics?.by_state?.["DONE"] ?? 0}</span>
          <span className="metric-l">done</span>
        </div>
        <div className="metric">
          <span className="metric-v">{perf ? perf.throughput_sps.toFixed(1) : "-"}</span>
          <span className="metric-l">sess/s</span>
        </div>
        <div className="metric">
          <span className="metric-v">{perf ? `${perf.duration_ms.p95}` : "-"}</span>
          <span className="metric-l">p95 ms</span>
        </div>
      </div>

      {perf && (
        <div className="perf-summary muted">
          부하: total={perf.total} ok={perf.success} fail={perf.failed} · pkts=
          {perf.total_packets} · setup p95={perf.setup_latency_ms.p95}ms · wall={perf.wall_ms}ms
        </div>
      )}

      <div className="chan-counts">
        {Object.entries(byChannel).map(([c, n]) => (
          <span key={c} className="chip">
            {c}: {n}
          </span>
        ))}
      </div>
    </div>
  );
}
