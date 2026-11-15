import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { usePoll } from "../hooks";
import { Badge, Card, Progress, btn, dur, fmt, isActiveRun, money, size } from "../ui";

export function Runs() {
  const { data: runs, error } = usePoll(() => api.runs(), [], 2000);
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Execuções</h1>
      <p className="text-sm text-slate-500">Execuções são iniciadas a partir de uma <Link to="/linhas" className="text-blue-600 underline">linha de produção</Link>.</p>
      {error && <p className="text-sm text-red-600">Falha ao carregar execuções.</p>}
      <Card>
        {runs && runs.length === 0 && <p className="text-sm text-slate-500">Nenhuma execução ainda.</p>}
        <ul className="divide-y divide-slate-100">
          {runs?.map((r) => (
            <li key={r.id}>
              <Link to={`/execucoes/${r.id}`} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm hover:bg-slate-50">
                <span><span className="font-mono text-xs text-slate-500">{r.id.slice(0, 8)}</span> · {r.line_name ?? r.pipeline}
                  <span className="ml-2 text-slate-400">{fmt(r.created_at)} · {money(r.cost)}</span></span>
                <span className="flex items-center gap-3"><Progress done={r.steps_done} total={r.steps_total} /><Badge status={r.status} /></span>
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
  const [tick, setTick] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);
  const { data: run, error } = usePoll(() => api.run(id), [id, tick], 1000, (r) => isActiveRun(r.status));
  const { data: logs } = usePoll(() => api.runLogs(id), [id, tick, run?.status], 2000, () => !!run && isActiveRun(run.status));
  const act = async (fn: () => Promise<unknown>) => {
    setMsg(null);
    try { await fn(); setTick((t) => t + 1); } catch (e) { setMsg((e as Error).message); }
  };
  if (error && !run) return <p className="text-sm text-red-600">Execução não encontrada.</p>;
  if (!run) return <p className="text-sm text-slate-500">Carregando…</p>;
  return (
    <div className="space-y-6">
      <div>
        <Link to={run.line_id ? `/linhas/${run.line_id}` : "/execucoes"} className="text-sm text-blue-600 hover:underline">← {run.line_name ?? "Execuções"}</Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">Execução <span className="font-mono text-lg">{run.id.slice(0, 8)}</span></h1>
            <Badge status={run.status} />
          </div>
          <div className="flex gap-2">
            {isActiveRun(run.status) && <button className={btn} data-testid="cancel-run" disabled={run.cancel_requested} onClick={() => act(() => api.cancel(id))}>
              {run.cancel_requested ? "Cancelando…" : "Cancelar"}</button>}
            {(run.status === "failed" || run.status === "cancelled") && <button className={btn} data-testid="resume-run" onClick={() => act(() => api.resume(id))}>Retomar</button>}
          </div>
        </div>
        <p className="mt-1 text-xs text-slate-500">Criada em {fmt(run.created_at)} · {run.trigger === "schedule" ? "agendada" : "manual"} · duração {dur(run.started_at, run.finished_at)} · custo {money(run.cost)}</p>
        {run.error && <p className="mt-2 text-sm text-red-600" data-testid="run-error">{run.error}</p>}
        {msg && <p className="mt-2 text-sm text-red-600">{msg}</p>}
      </div>
      <Card title="Etapas">
        <ol className="space-y-3">
          {run.steps.map((s) => (
            <li key={s.position} data-testid="step" className="rounded-lg border border-slate-200 p-3 text-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium">{s.position}. {s.name}</div>
                  <div className="text-xs text-slate-500">{s.message ?? "—"} · {dur(s.started_at, s.finished_at)} · {money(s.cost)}{s.total_attempts > 1 ? ` · ${s.total_attempts} tentativas` : ""}</div>
                </div>
                <Badge status={s.status} />
              </div>
              {s.output && (
                <details className="mt-2"><summary className="cursor-pointer text-xs text-slate-500">Entrada / saída</summary>
                  <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify({ input: s.input, output: s.output }, null, 2)}</pre></details>
              )}
            </li>
          ))}
        </ol>
      </Card>
      <Card title="Logs">
        {logs && logs.length === 0 && <p className="text-sm text-slate-500">Sem registros.</p>}
        <ul className="max-h-72 space-y-1 overflow-auto font-mono text-xs" data-testid="logs">
          {logs?.map((l, i) => (
            <li key={i} className={l.level === "error" ? "text-red-600" : l.level === "warn" ? "text-amber-700" : "text-slate-600"}>
              <span className="text-slate-400">{new Date(l.created_at).toLocaleTimeString("pt-BR")}</span> {l.step_name ? `[${l.step_name}] ` : ""}{l.message}</li>
          ))}
        </ul>
      </Card>
      <Card title="Artefatos">
        {run.artifacts.length === 0 && <p className="text-sm text-slate-500">Nenhum artefato gerado ainda.</p>}
        {run.artifacts.map((a) => (
          <div key={a.id} className="flex items-center justify-between gap-3 text-sm">
            <span>{a.filename} <span className="text-slate-400">({size(a.size)}{a.model ? ` · ${a.provider} / ${a.model}` : ""})</span></span>
            <a href={api.downloadUrl(a.id)} data-testid="download" className={btn}>Baixar</a>
          </div>
        ))}
      </Card>
    </div>
  );
}
