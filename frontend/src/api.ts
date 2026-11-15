export type Step = {
  position: number; name: string; status: string; message: string | null;
  started_at: string | null; finished_at: string | null;
};
export type Artifact = { id: string; filename: string; content_type: string; size: number; created_at: string };
export type Run = {
  id: string; pipeline: string; status: string; error: string | null;
  created_at: string; started_at: string | null; finished_at: string | null;
  steps: Step[]; artifacts: Artifact[];
};
export type Ready = { status: string; checks: Record<string, string> };

async function j<T>(res: Response): Promise<T> {
  if (!res.ok && res.status !== 503) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export const api = {
  startRun: () =>
    fetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pipeline: "demo" }) }).then(j<Run>),
  runs: () => fetch("/api/runs").then(j<Run[]>),
  run: (id: string) => fetch(`/api/runs/${id}`).then(j<Run>),
  artifacts: () => fetch("/api/artifacts").then(j<Artifact[]>),
  ready: () => fetch("/api/health/ready").then(j<Ready>),
  downloadUrl: (id: string) => `/api/artifacts/${id}/download`,
};
