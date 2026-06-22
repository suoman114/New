// 성능/메트릭 패널 (확장 지점). /api/metrics 폴링 + 채널별 이벤트 카운트.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { FlowEvent, Metrics } from "../api/types";

export function PerfPanel(props: { events: FlowEvent[] }) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  useEffect(() => {
    const tick = () => api.metrics().then(setMetrics).catch(() => {});
    tick();
    const t = setInterval(tick, 2000);
    return () => clearInterval(t);
  }, []);

  const byChannel = props.events.reduce<Record<string, number>>((acc, e) => {
    acc[e.channel] = (acc[e.channel] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="panel perf">
      <div className="panel-head">
        <h3>성능 / 메트릭</h3>
      </div>
      <div className="metrics">
        <div className="metric">
          <span className="metric-v">{metrics?.sessions_total ?? 0}</span>
          <span className="metric-l">sessions</span>
        </div>
        <div className="metric">
          <span className="metric-v">{metrics?.by_state?.["RUNNING"] ?? 0}</span>
          <span className="metric-l">running</span>
        </div>
        <div className="metric">
          <span className="metric-v">{metrics?.by_state?.["DONE"] ?? 0}</span>
          <span className="metric-l">done</span>
        </div>
        <div className="metric">
          <span className="metric-v">{metrics?.events_buffered ?? 0}</span>
          <span className="metric-l">events</span>
        </div>
      </div>
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
