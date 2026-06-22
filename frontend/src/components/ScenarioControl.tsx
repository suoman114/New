// 시나리오 선택/옵션/시작·중지.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ScenarioInfo } from "../api/types";

export function ScenarioControl(props: {
  onRan: (ids: string[]) => void;
  onScenario: (id: string) => void;
  connected: boolean;
}) {
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [sessionCount, setSessionCount] = useState(1);
  const [realtime, setRealtime] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = (id: string) => {
    setSelected(id);
    props.onScenario(id);
  };

  useEffect(() => {
    api
      .scenarios()
      .then((s) => {
        setScenarios(s);
        if (s.length) pick(s[0].id);
      })
      .catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.run(selected, { session_count: sessionCount, realtime });
      props.onRan(r.session_ids);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>시나리오 제어</h3>
        <span className={"dot " + (props.connected ? "on" : "off")} title="WebSocket">
          {props.connected ? "live" : "off"}
        </span>
      </div>
      <label>
        시나리오
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          {scenarios.map((s) => (
            <option key={s.id} value={s.id}>
              {s.id} ({s.service_type})
            </option>
          ))}
        </select>
      </label>
      <label>
        세션 수
        <input
          type="number"
          min={1}
          max={50}
          value={sessionCount}
          onChange={(e) => setSessionCount(Number(e.target.value))}
        />
      </label>
      <label className="row">
        <input type="checkbox" checked={realtime} onChange={(e) => setRealtime(e.target.checked)} />
        실시간(20ms 페이싱)
      </label>
      <button className="primary" onClick={run} disabled={busy || !selected}>
        {busy ? "실행 중..." : "▶ 시작"}
      </button>
      {error && <div className="error">{error}</div>}
    </div>
  );
}
