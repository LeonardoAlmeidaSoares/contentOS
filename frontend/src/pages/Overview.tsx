import { Link } from "react-router-dom";
import { api } from "../api";
import { usePoll } from "../hooks";
import { Badge, Card } from "../ui";

export function Overview() {
  const { data: ready, error } = usePoll(api.ready, [], 5000);
  const { data: runs } = usePoll(api.runs, [], 5000);
  const ok = runs?.filter((r) => r.status === "succeeded").length ?? 0;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Visão Geral</h1>
      <Card title="Saúde da infraestrutura">
        {error && <p className="text-sm text-red-600">API inacessível.</p>}
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {ready && Object.entries(ready.checks).map(([k, v]) => (
            <li key={k} className="flex items-center justify-between rounded-lg border border-slate-200 px-4 py-3 text-sm">
              <span className="capitalize">{k}</span><Badge status={v === "ok" ? "ok" : "failed"} />
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Execuções" action={<Link to="/execucoes" className="text-sm text-blue-600 hover:underline">Ver todas</Link>}>
        <p className="text-sm text-slate-600">{runs ? `${runs.length} execuções registradas, ${ok} concluídas.` : "Carregando…"}</p>
        <p className="mt-2 text-xs text-slate-400">Métricas de custo, receita e rentabilidade ainda não estão disponíveis.</p>
      </Card>
    </div>
  );
}
