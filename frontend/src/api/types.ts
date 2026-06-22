// 백엔드(api/) pydantic 모델과 1:1 대응하는 타입.

export type Channel = "SIP" | "RTP" | "RMQ" | "DB" | "VALIDATION" | "SYS";
export type Severity = "info" | "warn" | "error";

export interface FlowEvent {
  event_id: string;
  ts: number;
  session_id: string;
  call_id: string | null;
  channel: Channel;
  direction: string; // SIM->SUT | SUT->SIM | SUT-INTERNAL | SIM-INTERNAL
  peer: string;
  label: string;
  summary: string;
  payload: Record<string, unknown>;
  log_ref: string;
  severity: Severity;
}

export interface ScenarioInfo {
  id: string;
  title: string;
  service_type: string;
  floor_count: number;
}

export interface SessionInfo {
  session_id: string;
  scenario_id: string;
  call_id: string | null;
  service_type: string | null;
  state: "INIT" | "RUNNING" | "VALIDATING" | "DONE" | "ERROR";
  started_ms: number;
  ended_ms: number | null;
  validation_passed: boolean | null;
  summary: string;
}

export interface ValidationItem {
  category: "FILE" | "DB" | "AUDIO" | "RMQ" | "STATS";
  name: string;
  status: "PASS" | "FAIL" | "SKIP";
  expected?: unknown;
  actual?: unknown;
  detail: string;
}

export interface ValidationResult {
  session_id: string;
  call_id: string | null;
  items: ValidationItem[];
}

export interface LogLine {
  ts: number;
  level: string;
  message: string;
  session_id: string;
  call_id: string | null;
  extra: Record<string, unknown>;
}

export interface EventLogs {
  event_id: string;
  event: FlowEvent | null;
  payload: Record<string, unknown>;
  raw: string | null;
  logs: LogLine[];
}

export interface Metrics {
  sessions_total: number;
  by_state: Record<string, number>;
  events_buffered: number;
  ws_subscribers: number;
}

export interface PerfSummary {
  total: number;
  success: number;
  failed: number;
  failure_rate: number;
  throughput_sps: number;
  duration_ms: { p50: number; p95: number; p99: number };
  setup_latency_ms: { p50: number; p95: number };
  total_packets: number;
  wall_ms: number;
}

export interface IntegrationHealth {
  db: { reachable: boolean; table: string; host: string; database: string };
  rmq: { enabled: boolean; host: string; tracked_calls: number };
  fs: { active_root: string | null; ramdisk: boolean; nas: boolean };
  inject_mode: string;
}
