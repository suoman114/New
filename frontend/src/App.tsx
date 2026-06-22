import { useEffect, useState } from "react";
import { useFlowSocket } from "./api/useFlowSocket";
import { api } from "./api/client";
import type { FlowEvent, IntegrationHealth } from "./api/types";
import { ScenarioControl } from "./components/ScenarioControl";
import { LadderDiagram } from "./components/LadderDiagram";
import { LogDrawer } from "./components/LogDrawer";
import { SessionTable } from "./components/SessionTable";
import { ValidationReport } from "./components/ValidationReport";
import { PerfPanel } from "./components/PerfPanel";

export default function App() {
  const { events, connected } = useFlowSocket(300);
  const [selected, setSelected] = useState<FlowEvent | null>(null);
  const [filterCallId, setFilterCallId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [scenarioId, setScenarioId] = useState<string>("");
  const [health, setHealth] = useState<IntegrationHealth | null>(null);

  useEffect(() => {
    const tick = () => api.integrationHealth().then(setHealth).catch(() => {});
    tick();
    const t = setInterval(tick, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <h1>uVCS 검증 자동화 시뮬레이터</h1>
        <span className="sub">LTE-R 녹취서버 (MCPTT/IMS) 검증 대시보드</span>
        {health && (
          <span className="health">
            <span className={"dot " + (health.db.reachable ? "on" : "off")}>DB</span>
            <span className={"dot " + (health.rmq.enabled ? "on" : "off")}>RMQ</span>
            <span className={"dot " + (health.fs.active_root ? "on" : "off")}>FS</span>
            <span className="sub">{health.inject_mode}</span>
          </span>
        )}
      </header>

      <div className="layout">
        <aside className="left">
          <ScenarioControl
            connected={connected}
            onRan={() => setRefreshKey((k) => k + 1)}
            onScenario={setScenarioId}
          />
          <SessionTable refreshKey={refreshKey} activeCallId={filterCallId} onPick={setFilterCallId} />
          <ValidationReport events={events} />
        </aside>

        <main className="center">
          <LadderDiagram
            events={events}
            selected={selected?.event_id ?? null}
            onSelect={setSelected}
            filterCallId={filterCallId}
          />
          <PerfPanel events={events} scenarioId={scenarioId} />
        </main>

        <aside className="right">
          <LogDrawer event={selected} onClose={() => setSelected(null)} />
        </aside>
      </div>
    </div>
  );
}
