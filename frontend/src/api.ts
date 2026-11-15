export type Step = {
  position: number; name: string; status: string; message: string | null;
  input: Record<string, unknown> | null; output: Record<string, unknown> | null;
  cost: number; attempts: number; total_attempts: number;
  started_at: string | null; finished_at: string | null;
};
export type Artifact = {
  id: string; run_id: string; step_name: string | null; filename: string; content_type: string; size: number;
  provider: string | null; model: string | null; meta: Record<string, number> | null; created_at: string;
};
export type RunSummary = {
  id: string; line_id: string | null; line_name: string | null; pipeline: string; trigger: string; status: string;
  error: string | null; cost: number; cancel_requested: boolean;
  created_at: string; started_at: string | null; finished_at: string | null; steps_total: number; steps_done: number;
};
export type Run = RunSummary & { steps: Step[]; artifacts: Artifact[] };
export type RunLog = { step_name: string | null; level: string; message: string; created_at: string };
export type Line = {
  id: string; name: string; description: string; pipeline: string; active: boolean;
  config: Record<string, unknown>; interval_minutes: number | null;
  cost_limit_run: number | null; cost_limit_month: number | null; max_attempts: number; backoff_seconds: number;
  last_run_at: string | null; next_run_at: string | null; archived_at: string | null; created_at: string;
  cost_month: number; cost_total: number; products: number;
  active_run: RunSummary | null; last_run: RunSummary | null;
};
export type LineInput = Partial<Omit<Line, "id" | "created_at" | "active" | "last_run_at" | "next_run_at" | "archived_at" | "cost_month" | "cost_total" | "products" | "active_run" | "last_run">> & { name: string; pipeline: string };
export type Pipeline = { name: string; label: string; description: string; default_config: Record<string, unknown>; steps: string[] };
export type Ready = { status: string; checks: Record<string, string> };

export type ModelCfg = {
  id: string; capabilities: string[]; active?: boolean; note?: string;
  supports?: { aspect_ratios?: string[]; qualities?: string[]; resolutions?: string[]; max_n?: number; negative_prompt?: boolean; reference_images?: boolean };
  pricing?: Record<string, unknown>;
};
export type Provider = {
  id: string; name: string; service: string; service_label: string; base_url: string | null;
  has_credentials: boolean; credentials_hint: string | null; config: Record<string, unknown>;
  models: ModelCfg[]; capabilities: string[]; active: boolean; status: string; status_message: string | null;
  status_checked_at: string | null; limit_month_usd: number | null; month_cost: number; created_at: string;
};
export type Service = { service: string; label: string; default_base_url: string | null; needs_key: boolean; capabilities: string[]; known_models: ModelCfg[]; pricing_source: string };
export type ProviderInput = { name: string; service?: string; base_url?: string | null; api_key?: string; clear_credentials?: boolean; config?: Record<string, unknown>; models?: ModelCfg[]; limit_month_usd?: number | null };
export type Usage = {
  id: string; model: string; capability: string; scope: string; run_id: string | null; status: string;
  cost_estimated: number; cost_actual: number | null; cost_effective: number; cost_source: string; cost_unknown: boolean;
  input_tokens: number | null; output_tokens: number | null; images: number; duration_ms: number | null;
  request_id: string | null; error: string | null; created_at: string;
};
export type UsageResp = { items: Usage[]; month: { spent: number; limit: number | null; reconciled_calls: number; reconciled_estimated: number; reconciled_actual: number; failures: number } };

export type Target = { provider_id: string; model: string };
export type LabParams = {
  targets: Target[]; aspect_ratio: string; resolution: string; quality: string; n: number;
  system?: string | null; max_tokens: number; references: string[]; allow_unknown_cost: boolean;
};
export type LabRequest = LabParams & { kind: "image" | "text"; prompt: string; negative_prompt?: string | null };
export type PlanRow = { provider_id: string; provider_name: string; model: string; cost: number | null; basis: string; error: string | null };
export type Estimate = { targets: PlanRow[]; total_known: number; has_unknown: boolean; has_error: boolean; lab_month_spent: number; lab_month_limit: number };
export type LabResult = {
  id: string; provider_id: string; provider_name: string; model: string; run_id: string | null; status: string; error: string | null;
  text: string | null; rating: number | null; notes: string;
  images: { artifact_id: string; filename: string; width: number | null; height: number | null; size: number }[];
  duration_ms: number | null; cost_estimated: number | null; cost_effective: number | null; cost_source: string | null; cost_unknown: boolean;
  input_tokens: number | null; output_tokens: number | null;
};
export type Experiment = {
  id: string; kind: string; label: string | null; batch_id: string | null; prompt: string; negative_prompt: string | null;
  params: Record<string, unknown>; created_at: string; results: LabResult[]; total_cost: number;
};
export type BenchPrompt = { id: string; category: string; prompt: string; negative_prompt: string };
export type BenchEstimate = { prompts: number; generations: number; targets: { provider_name: string; model: string; cost: number; unknown: boolean; error: string | null }[]; total_known: number; has_unknown: boolean; has_error: boolean; lab_month_spent: number; lab_month_limit: number };

async function call<T>(method: string, url: string, body?: unknown, raw?: FormData): Promise<T> {
  const res = await fetch(url, {
    method, credentials: "same-origin",
    headers: raw || body === undefined ? undefined : { "Content-Type": "application/json" },
    body: raw ?? (body === undefined ? undefined : JSON.stringify(body)),
  });
  if (res.status === 401 && !url.includes("/auth/login")) window.dispatchEvent(new Event("unauthorized"));
  if (res.status === 503 && url.includes("/health/ready")) return res.json();
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
const get = <T,>(u: string) => call<T>("GET", u);
const post = <T,>(u: string, b?: unknown) => call<T>("POST", u, b);
const patch = <T,>(u: string, b: unknown) => call<T>("PATCH", u, b);

export const api = {
  login: (token: string) => post<{ ok: boolean }>("/api/auth/login", { token }),
  logout: () => post("/api/auth/logout"),
  me: () => get<{ ok: boolean }>("/api/auth/me"),
  lines: (archived = false) => get<Line[]>(`/api/lines${archived ? "?include_archived=true" : ""}`),
  line: (id: string) => get<Line>(`/api/lines/${id}`),
  createLine: (b: LineInput) => post<Line>("/api/lines", b),
  updateLine: (id: string, b: Partial<LineInput>) => patch<Line>(`/api/lines/${id}`, b),
  lineAction: (id: string, a: "activate" | "deactivate" | "archive" | "unarchive") => post<Line>(`/api/lines/${id}/${a}`),
  runLine: (id: string) => post<Run>(`/api/lines/${id}/run`),
  pipelines: () => get<Pipeline[]>("/api/pipelines"),
  runs: (lineId?: string) => get<RunSummary[]>(`/api/runs${lineId ? `?line_id=${lineId}` : ""}`),
  run: (id: string) => get<Run>(`/api/runs/${id}`),
  runLogs: (id: string) => get<RunLog[]>(`/api/runs/${id}/logs`),
  cancel: (id: string) => post<Run>(`/api/runs/${id}/cancel`),
  resume: (id: string) => post<Run>(`/api/runs/${id}/resume`),
  artifacts: (lineId?: string) => get<Artifact[]>(`/api/artifacts${lineId ? `?line_id=${lineId}` : ""}`),
  ready: () => get<Ready>("/api/health/ready"),
  downloadUrl: (id: string) => `/api/artifacts/${id}/download`,
  imageUrl: (id: string) => `/api/artifacts/${id}/download?inline=1`,
  services: () => get<Service[]>("/api/providers/services"),
  providers: () => get<Provider[]>("/api/providers"),
  provider: (id: string) => get<Provider>(`/api/providers/${id}`),
  createProvider: (b: ProviderInput) => post<Provider>("/api/providers", b),
  updateProvider: (id: string, b: ProviderInput) => patch<Provider>(`/api/providers/${id}`, b),
  providerAction: (id: string, a: "activate" | "deactivate" | "test") => post<Provider>(`/api/providers/${id}/${a}`),
  usage: (id: string) => get<UsageResp>(`/api/providers/${id}/usage`),
  labEstimate: (b: LabRequest) => post<Estimate>("/api/lab/estimate", b),
  labCreate: (b: LabRequest) => post<Experiment>("/api/lab/experiments", b),
  experiments: () => get<Experiment[]>("/api/lab/experiments"),
  experiment: (id: string) => get<Experiment>(`/api/lab/experiments/${id}`),
  rate: (id: string, b: { rating?: number | null; notes?: string }) => patch<LabResult>(`/api/lab/results/${id}`, b),
  uploadRef: (file: File) => { const f = new FormData(); f.append("file", file); return call<{ key: string; size: number }>("POST", "/api/lab/references", undefined, f); },
  benchPrompts: () => get<BenchPrompt[]>("/api/lab/benchmark"),
  benchEstimate: (b: LabParams) => post<BenchEstimate>("/api/lab/benchmark/estimate", b),
  benchRun: (b: LabParams & { confirm_total_usd: number }) => post<{ batch_id: string; experiments: string[]; estimated_total: number }>("/api/lab/benchmark/run", b),
};
