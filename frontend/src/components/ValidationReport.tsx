// 검증 리포트: 파일/DB/오디오/RMQ 항목별 PASS/FAIL + diff. (VALIDATION 이벤트 기반)
import type { FlowEvent, ValidationItem } from "../api/types";

interface PayloadWithItems {
  items?: ValidationItem[];
}

export function ValidationReport(props: { events: FlowEvent[] }) {
  // 가장 최근 VALIDATION 이벤트의 항목을 표시
  const last = [...props.events].reverse().find((e) => e.channel === "VALIDATION");
  const items = (last?.payload as PayloadWithItems | undefined)?.items ?? [];
  const fails = items.filter((i) => i.status === "FAIL").length;

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>검증 리포트</h3>
        {last && (
          <span className={"badge " + (fails === 0 ? "pass" : "fail")}>
            {fails === 0 ? "PASS" : `FAIL ${fails}`}
          </span>
        )}
      </div>
      {!last && <div className="muted">검증 결과 없음 — 실행/검증 후 표시됩니다.</div>}
      {last && (
        <table className="grid">
          <thead>
            <tr>
              <th>cat</th>
              <th>name</th>
              <th>status</th>
              <th>detail</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={i}>
                <td>{it.category}</td>
                <td className="mono">{it.name}</td>
                <td>
                  <span className={"state " + (it.status === "PASS" ? "DONE" : it.status === "FAIL" ? "ERROR" : "INIT")}>
                    {it.status}
                  </span>
                </td>
                <td className="muted">{it.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
