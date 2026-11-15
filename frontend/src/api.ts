export type Step = {
  position: number; name: string; status: string; message: string | null;
  input: Record<string, unknown> | null; output: Record<string, unknown> | null;
  cost: number; attempts: number; total_attempts: number;
  started_at: string | null; finished_at: string | null;
};
export type Artifact = {
  id: string; run_id: string; step_name: string | null; filename: string; content_type: string; size: number; created_at: string;
};
export type RunSummary = {
  id: string; line_id: string | null; line_name: string | null; pipeline: string; trigger: string; status: string;
  error: string | null; cost: number; cancel_requested: boolean;
  created_at: string; started_at: string | null; finished_at: string | null; steps_total: number; steps_done: number;
};
export type Run = RunSummary & { steps: Step[]; artifacts: Artifact[] };
export type Line = {
  id: string; name: string; description: string; pipeline: string; active: boolean;
  config: Record<string, unknown>; interval_minutes: number | null;
  cost_limit_run: number | null; cost_limit_month: number | null; max_attempts: number; backoff_seconds: number;
  last_run_at: string | null; next_run_at: string | null; created_at: string;
  cost_month: number; cost_total: number; products: number;
  active_run: RunSummary | null; last_run: RunSummary | null;
};
export type LineInput = Partial<Omit<Line, "id" | "created_at" | "active" | "last_run_at" | "next_run_at" | "cost_month" | "cost_total" | "products" | "active_run" | "last_run">> & { name: string; pipeline: string };
export type Pipeline = { name: string; label: string; description: string; default_config: Record<string, unknown>; steps: string[] };
export type Ready = { status: string; checks: Record<string, string> };

async function j<T>(res: Response): Promise<T> {
  if (res.status === 503) return res.json();
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const b = await res.json();
      detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch { /* corpo não-JSON */ }
    throw new Error(detail);
  }
  return res.json();
}
const send = (method: string, url: string, body?: unknown) =>
  fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  lines: () => fetch("/api/lines").then(j<Line[]>),
  line: (id: string) => fetch(`/api/lines/${id}`).then(j<Line>),
  createLine: (b: LineInput) => send("POST", "/api/lines", b).then(j<Line>),
  updateLine: (id: string, b: Partial<LineInput>) => send("PATCH", `/api/lines/${id}`, b).then(j<Line>),
  lineAction: (id: string, a: "activate" | "deactivate") => send("POST", `/api/lines/${id}/${a}`).then(j<Line>),
  runLine: (id: string) => send("POST", `/api/lines/${id}/run`).then(j<Run>),
  pipelines: () => fetch("/api/pipelines").then(j<Pipeline[]>),
  runs: (lineId?: string) => fetch(`/api/runs${lineId ? `?line_id=${lineId}` : ""}`).then(j<RunSummary[]>),
  run: (id: string) => fetch(`/api/runs/${id}`).then(j<Run>),
  cancel: (id: string) => send("POST", `/api/runs/${id}/cancel`).then(j<Run>),
  resume: (id: string) => send("POST", `/api/runs/${id}/resume`).then(j<Run>),
  artifacts: (lineId?: string) => fetch(`/api/artifacts${lineId ? `?line_id=${lineId}` : ""}`).then(j<Artifact[]>),
  ready: () => fetch("/api/health/ready").then(j<Ready>),
  downloadUrl: (id: string) => `/api/artifacts/${id}/download`,
};
