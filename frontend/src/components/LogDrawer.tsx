// 메시지 클릭 → raw + 파싱 결과(payload) + 관련 로그 라인 표시.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { EventLogs, FlowEvent } from "../api/types";

export function LogDrawer(props: { event: FlowEvent | null; onClose: () => void }) {
  const [data, setData] = useState<EventLogs | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    if (!props.event) return;
    api
      .eventLogs(props.event.event_id)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [props.event]);

  if (!props.event) {
    return (
      <div className="drawer">
        <div className="drawer-hint">ladder 에서 메시지를 클릭하면 로그가 표시됩니다.</div>
      </div>
    );
  }

  const ev = props.event;
  return (
    <div className="drawer">
      <div className="drawer-head">
        <strong>{ev.label}</strong>
        <button onClick={props.onClose}>✕</button>
      </div>
      <div className="drawer-meta">
        <div>
          <span className="tag">{ev.channel}</span>
          <span className="tag">{ev.direction}</span>
          <span className="tag">{ev.peer}</span>
        </div>
        <div className="muted">call_id: {ev.call_id ?? "-"}</div>
        <div className="muted">{ev.summary}</div>
      </div>

      {error && <div className="error">{error}</div>}

      <section>
        <h4>파싱 결과 (payload)</h4>
        <pre className="code">{JSON.stringify(ev.payload, null, 2)}</pre>
      </section>

      {data?.raw && (
        <section>
          <h4>raw</h4>
          <pre className="code raw">{data.raw}</pre>
        </section>
      )}

      <section>
        <h4>관련 로그 ({data?.logs.length ?? 0})</h4>
        <div className="logs">
          {(data?.logs ?? []).map((ln, i) => (
            <div key={i} className={"logline " + ln.level}>
              <span className="logline-lvl">{ln.level}</span>
              {ln.message}
            </div>
          ))}
          {data && data.logs.length === 0 && <div className="muted">로그 없음</div>}
        </div>
      </section>
    </div>
  );
}
