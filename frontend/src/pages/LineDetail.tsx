import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { usePoll } from "../hooks";
import { Badge, Card, Progress, btn, btnPrimary, fmt, money, size } from "../ui";

export function LineDetail() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [msg, setMsg] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const { data: line, error } = usePoll(() => api.line(id), [id, tick], 1500);
  const { data: runs } = usePoll(() => api.runs(id), [id, tick], 1500);
  const { data: arts } = usePoll(() => api.artifacts(id), [id, tick], 3000);

  const act = async (fn: () => Promise<unknown>, after?: (r: any) => void) => {
    setMsg(null);
    try { const r = await fn(); after?.(r); setTick((t) => t + 1); } catch (e) { setMsg((e as Error).message); }
  };
  if (error && !line) return <p className="text-sm text-red-600">Linha não encontrada.</p>;
  if (!line) return <p className="text-sm text-slate-500">Carregando…</p>;
  return (
    <div className="space-y-6">
      <div>
        <Link to="/linhas" className="text-sm text-blue-600 hover:underline">← Linhas de Produção</Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold" data-testid="line-title">{line.name}</h1>
            <Badge status={line.active ? "active" : "inactive"} />
          </div>
          <div className="flex flex-wrap gap-2">
            <button className={btnPrimary} data-testid="run-line" disabled={!line.active || !!line.active_run}
              title={!line.active ? "Ative a linha para executar" : line.active_run ? "Já existe execução ativa" : ""}
              onClick={() => act(() => api.runLine(id), (r) => nav(`/execucoes/${r.id}`))}>Executar agora</button>
            <button className={btn} data-testid="toggle-line" onClick={() => act(() => api.lineAction(id, line.active ? "deactivate" : "activate"))}>
              {line.active ? "Desativar" : "Ativar"}</button>
            <Link className={btn} to={`/linhas/${id}/editar`}>Editar</Link>
          </div>
        </div>
        {line.description && <p className="mt-1 text-sm text-slate-500">{line.description}</p>}
        {msg && <p className="mt-2 text-sm text-red-600" data-testid="action-error">{msg}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[["Última execução", fmt(line.last_run_at)], ["Próxima execução", fmt(line.next_run_at)],
          ["Custo no mês", `${money(line.cost_month)} / ${money(line.cost_limit_month)}`], ["Produtos gerados", String(line.products)]].map(([k, v]) => (
          <div key={k} className="rounded-xl border border-slate-200 bg-white p-4 text-sm"><div className="text-xs text-slate-400">{k}</div><div className="mt-1 font-medium">{v}</div></div>
        ))}
      </div>

      <Card title="Configurações">
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div><dt className="text-xs text-slate-400">Pipeline</dt><dd>{line.pipeline}</dd></div>
          <div><dt className="text-xs text-slate-400">Frequência</dt><dd>{line.interval_minutes ? `a cada ${line.interval_minutes} min` : "somente manual"}</dd></div>
          <div><dt className="text-xs text-slate-400">Limite por execução</dt><dd>{money(line.cost_limit_run)}</dd></div>
          <div><dt className="text-xs text-slate-400">Retry</dt><dd>{line.max_attempts} tentativas, backoff {line.backoff_seconds}s ×2</dd></div>
        </dl>
        <pre className="mt-4 overflow-x-auto rounded-lg bg-slate-50 p-3 text-xs">{JSON.stringify(line.config, null, 2)}</pre>
      </Card>

      <Card title="Histórico de execuções">
        {runs && runs.length === 0 && <p className="text-sm text-slate-500">Nenhuma execução ainda.</p>}
        <ul className="divide-y divide-slate-100">
          {runs?.map((r) => (
            <li key={r.id}>
              <Link to={`/execucoes/${r.id}`} data-testid="run-row" className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm hover:bg-slate-50">
                <span><span className="font-mono text-xs text-slate-500">{r.id.slice(0, 8)}</span>
                  <span className="ml-2 text-slate-400">{fmt(r.created_at)} · {r.trigger === "schedule" ? "agendada" : "manual"} · {money(r.cost)}</span></span>
                <span className="flex items-center gap-3"><Progress done={r.steps_done} total={r.steps_total} /><Badge status={r.status} /></span>
              </Link>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Produtos gerados">
        {arts && arts.length === 0 && <p className="text-sm text-slate-500">Nenhum produto gerado.</p>}
        <ul className="divide-y divide-slate-100">
          {arts?.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span>{a.filename} <span className="text-slate-400">({size(a.size)} · {fmt(a.created_at)})</span></span>
              <a className={btn} href={api.downloadUrl(a.id)}>Baixar</a>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
