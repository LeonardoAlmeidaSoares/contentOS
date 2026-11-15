import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { usePoll } from "../hooks";
import { Badge, Card, Progress, btnPrimary, fmt, money } from "../ui";

export function Lines() {
  const [archived, setArchived] = useState(false);
  const { data: lines, error } = usePoll(() => api.lines(archived), [archived], 2000);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Linhas de Produção</h1>
        <label className="flex items-center gap-2 text-sm text-slate-500"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} data-testid="show-archived" />Mostrar arquivadas</label>
        <Link to="/linhas/nova" className={btnPrimary} data-testid="new-line">Nova linha</Link>
      </div>
      {error && <p className="text-sm text-red-600">Falha ao carregar linhas.</p>}
      {lines && lines.length === 0 && <Card><p className="text-sm text-slate-500">Nenhuma linha cadastrada. Crie uma com o pipeline de demonstração para validar o motor.</p></Card>}
      <div className="grid gap-4">
        {lines?.map((l) => (
          <Link key={l.id} to={`/linhas/${l.id}`} data-testid="line-card"
            className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm hover:border-slate-400">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2"><span className="font-medium">{l.name}</span><Badge status={l.archived_at ? "archived" : l.active ? "active" : "inactive"} /></div>
              {l.active_run
                ? <div className="flex items-center gap-2"><Badge status={l.active_run.status} /><Progress done={l.active_run.steps_done} total={l.active_run.steps_total} /></div>
                : l.last_run && <Badge status={l.last_run.status} />}
            </div>
            <p className="mt-1 text-xs text-slate-500">{l.pipeline}{l.description ? ` · ${l.description}` : ""}</p>
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600 sm:grid-cols-4">
              <div><dt className="text-slate-400">Última execução</dt><dd>{fmt(l.last_run_at)}</dd></div>
              <div><dt className="text-slate-400">Próxima execução</dt><dd>{fmt(l.next_run_at)}</dd></div>
              <div><dt className="text-slate-400">Custo (mês / total)</dt><dd>{money(l.cost_month)} / {money(l.cost_total)}</dd></div>
              <div><dt className="text-slate-400">Produtos gerados</dt><dd>{l.products}</dd></div>
            </dl>
          </Link>
        ))}
      </div>
    </div>
  );
}
