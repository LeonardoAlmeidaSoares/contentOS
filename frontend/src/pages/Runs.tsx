import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { usePoll } from "../hooks";
import { Badge, Card, dur, fmt, size } from "../ui";

export function Runs() {
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const { data: runs, error } = usePoll(api.runs, [], 2000);
  const start = async () => {
    setBusy(true);
    try { nav(`/execucoes/${(await api.startRun()).id}`); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Execuções</h1>
        <button onClick={start} disabled={busy} data-testid="start-run"
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50">
          Iniciar execução de demonstração
        </button>
      </div>
      {error && <p className="text-sm text-red-600">Falha ao carregar execuções.</p>}
      <Card>
        {runs && runs.length === 0 && <p className="text-sm text-slate-500">Nenhuma execução ainda.</p>}
        <ul className="divide-y divide-slate-100">
          {runs?.map((r) => (
            <li key={r.id}>
              <Link to={`/execucoes/${r.id}`} className="flex items-center justify-between gap-3 py-3 text-sm hover:bg-slate-50">
                <span><span className="font-mono text-xs text-slate-500">{r.id.slice(0, 8)}</span> · {r.pipeline}
                  <span className="ml-2 text-slate-400">{fmt(r.created_at)}</span></span>
                <Badge status={r.status} />
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

export function RunDetail() {
  const { id = "" } = useParams();
  const { data: run, error } = usePoll(() => api.run(id), [id], 1000, (r) => r.status === "queued" || r.status === "running");
  if (error && !run) return <p className="text-sm text-red-600">Execução não encontrada.</p>;
  if (!run) return <p className="text-sm text-slate-500">Carregando…</p>;
  return (
    <div className="space-y-6">
      <div>
        <Link to="/execucoes" className="text-sm text-blue-600 hover:underline">← Execuções</Link>
        <div className="mt-2 flex items-center gap-3">
          <h1 className="text-2xl font-semibold">Execução <span className="font-mono text-lg">{run.id.slice(0, 8)}</span></h1>
          <Badge status={run.status} />
        </div>
        <p className="mt-1 text-xs text-slate-500">Criada em {fmt(run.created_at)} · duração {dur(run.started_at, run.finished_at)}</p>
        {run.error && <p className="mt-2 text-sm text-red-600">{run.error}</p>}
      </div>
      <Card title="Etapas">
        <ol className="space-y-3">
          {run.steps.map((s) => (
            <li key={s.position} data-testid="step" className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 p-3 text-sm">
              <div>
                <div className="font-medium">{s.position}. {s.name}</div>
                <div className="text-xs text-slate-500">{s.message ?? "—"} · {dur(s.started_at, s.finished_at)}</div>
              </div>
              <Badge status={s.status} />
            </li>
          ))}
        </ol>
      </Card>
      <Card title="Artefatos">
        {run.artifacts.length === 0 && <p className="text-sm text-slate-500">Nenhum artefato gerado ainda.</p>}
        {run.artifacts.map((a) => (
          <div key={a.id} className="flex items-center justify-between gap-3 text-sm">
            <span>{a.filename} <span className="text-slate-400">({size(a.size)})</span></span>
            <a href={api.downloadUrl(a.id)} data-testid="download" className="rounded-lg border border-slate-300 px-3 py-1.5 hover:bg-slate-50">Baixar</a>
          </div>
        ))}
      </Card>
    </div>
  );
}
