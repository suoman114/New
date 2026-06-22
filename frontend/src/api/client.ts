// REST client (dashboard-backend).
import type {
  EventLogs,
  IntegrationHealth,
  Metrics,
  PerfSummary,
  ScenarioInfo,
  SessionInfo,
  ValidationResult,
} from "./types";

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return (await r.json()) as T;
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return (await r.json()) as T;
}

export const api = {
  scenarios: () => get<ScenarioInfo[]>("/api/scenarios"),
  run: (scenario_id: string, opts: { session_count?: number; realtime?: boolean } = {}) =>
    post<{ session_ids: string[] }>("/api/run", {
      scenario_id,
      session_count: opts.session_count ?? 1,
      realtime: opts.realtime ?? true,
      wait: false,
    }),
  stop: (session_id: string) =>
    post<{ stopped: boolean }>(`/api/stop?session_id=${session_id}`, {}),
  sessions: () => get<SessionInfo[]>("/api/sessions"),
  results: () => get<Record<string, ValidationResult>>("/api/results"),
  eventLogs: (eventId: string) => get<EventLogs>(`/api/events/${eventId}/logs`),
  metrics: () => get<Metrics>("/api/metrics"),
  perfRun: (scenario_id: string, total: number, cps: number, workers = 1) =>
    post<PerfSummary>("/api/perf/run", { scenario_id, total, cps, realtime: false, workers }),
  perfLast: () => get<PerfSummary>("/api/perf"),
  integrationHealth: () => get<IntegrationHealth>("/api/integration/health"),
  validate: (session_id: string) =>
    post<ValidationResult>(`/api/validate?session_id=${session_id}`, {}),
};
