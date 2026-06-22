// 호처리 흐름 ladder: 컬럼=노드, 세로=시간. 메시지 클릭 → 로그 드릴다운.
import type { Channel, FlowEvent, Severity } from "../api/types";

const NODES = ["UA-Caller", "VCTP", "VCSM", "VCMM_0", "VCMC", "DB", "validator", "scenario"];

const CHANNEL_COLOR: Record<Channel, string> = {
  SIP: "#2563eb",
  RTP: "#16a34a",
  RMQ: "#9333ea",
  DB: "#b45309",
  VALIDATION: "#dc2626",
  SYS: "#64748b",
};

function nodeIndex(peer: string): number {
  const i = NODES.indexOf(peer);
  return i >= 0 ? i : NODES.length - 1;
}

function arrow(direction: string): string {
  if (direction === "SIM->SUT") return "→";
  if (direction === "SUT->SIM") return "←";
  if (direction === "SUT-INTERNAL") return "⇄";
  return "•";
}

function sevBorder(sev: Severity): string {
  return sev === "error" ? "#dc2626" : sev === "warn" ? "#d97706" : "transparent";
}

export function LadderDiagram(props: {
  events: FlowEvent[];
  selected: string | null;
  onSelect: (ev: FlowEvent) => void;
  filterCallId: string | null;
}) {
  const events = props.filterCallId
    ? props.events.filter((e) => e.call_id === props.filterCallId)
    : props.events;

  return (
    <div className="ladder">
      <div className="ladder-head">
        {NODES.map((n) => (
          <div key={n} className="ladder-col-head">
            {n}
          </div>
        ))}
      </div>
      <div className="ladder-body">
        {events.map((ev) => {
          const col = nodeIndex(ev.peer);
          const t = new Date(ev.ts).toLocaleTimeString("ko-KR", { hour12: false });
          return (
            <div
              key={ev.event_id}
              className={"ladder-row" + (props.selected === ev.event_id ? " selected" : "")}
              onClick={() => props.onSelect(ev)}
              title={ev.summary}
            >
              <span className="ladder-ts">{t}</span>
              {NODES.map((_, i) => (
                <div key={i} className="ladder-cell">
                  {i === col && (
                    <span
                      className="ladder-msg"
                      style={{
                        background: CHANNEL_COLOR[ev.channel],
                        boxShadow: `0 0 0 2px ${sevBorder(ev.severity)}`,
                      }}
                    >
                      {arrow(ev.direction)} {ev.label}
                    </span>
                  )}
                </div>
              ))}
            </div>
          );
        })}
        {events.length === 0 && <div className="ladder-empty">이벤트 없음 — 시나리오를 실행하세요.</div>}
      </div>
    </div>
  );
}
