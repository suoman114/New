import { useState } from "react";
import { useFlowSocket } from "./api/useFlowSocket";
import type { FlowEvent } from "./api/types";
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

  return (
    <div className="app">
      <header className="topbar">
        <h1>uVCS 검증 자동화 시뮬레이터</h1>
        <span className="sub">LTE-R 녹취서버 (MCPTT/IMS) 검증 대시보드</span>
      </header>

      <div className="layout">
        <aside className="left">
          <ScenarioControl connected={connected} onRan={() => setRefreshKey((k) => k + 1)} />
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
          <PerfPanel events={events} />
        </main>

        <aside className="right">
          <LogDrawer event={selected} onClose={() => setSelected(null)} />
        </aside>
      </div>
    </div>
  );
}
