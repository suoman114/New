// 진행/완료 세션 테이블. 행 클릭 → call_id 로 ladder 필터, "검증" → 실 SUT 대조.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SessionInfo } from "../api/types";

export function SessionTable(props: {
  refreshKey: number;
  onPick: (callId: string | null) => void;
  activeCallId: string | null;
}) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const tick = () => api.sessions().then(setSessions).catch(() => {});

  useEffect(() => {
    tick();
    const t = setInterval(tick, 1500);
    return () => clearInterval(t);
  }, [props.refreshKey]);

  const validate = async (e: React.MouseEvent, sid: string) => {
    e.stopPropagation();
    setBusy(sid);
    try {
      await api.validate(sid);
      await tick();
    } catch {
      /* ignore */
    } finally {
      setBusy(null);
    }
  };

  const passLabel = (s: SessionInfo) =>
    s.validation_passed === null ? "-" : s.validation_passed ? "PASS" : "FAIL";

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>세션</h3>
        {props.activeCallId && <button onClick={() => props.onPick(null)}>필터 해제</button>}
      </div>
      <table className="grid">
        <thead>
          <tr>
            <th>session</th>
            <th>type</th>
            <th>state</th>
            <th>검증</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((s) => (
            <tr
              key={s.session_id}
              className={s.call_id && s.call_id === props.activeCallId ? "active" : ""}
              onClick={() => props.onPick(s.call_id)}
            >
              <td className="mono">{s.session_id.slice(0, 8)}</td>
              <td>{s.service_type ?? "-"}</td>
              <td>
                <span className={"state " + s.state}>{s.state}</span>
              </td>
              <td>
                <span
                  className={
                    "badge " +
                    (s.validation_passed === null ? "" : s.validation_passed ? "pass" : "fail")
                  }
                >
                  {passLabel(s)}
                </span>
              </td>
              <td>
                {s.state === "DONE" && (
                  <button onClick={(e) => validate(e, s.session_id)} disabled={busy === s.session_id}>
                    {busy === s.session_id ? "..." : "검증"}
                  </button>
                )}
              </td>
            </tr>
          ))}
          {sessions.length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                세션 없음
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
