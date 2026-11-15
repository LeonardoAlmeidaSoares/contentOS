import { Link } from "react-router-dom";
import { api } from "../api";
import { usePoll } from "../hooks";
import { Card, fmt, size } from "../ui";

export function Library() {
  const { data: items, error } = usePoll(api.artifacts, [], 5000);
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Biblioteca</h1>
      {error && <p className="text-sm text-red-600">Falha ao carregar artefatos.</p>}
      <Card>
        {items && items.length === 0 && <p className="text-sm text-slate-500">Nenhum artefato produzido.</p>}
        <ul className="divide-y divide-slate-100">
          {items?.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 py-3 text-sm">
              <span>{a.filename} <span className="text-slate-400">({size(a.size)} · {fmt(a.created_at)})</span></span>
              <a href={api.downloadUrl(a.id)} className="rounded-lg border border-slate-300 px-3 py-1.5 hover:bg-slate-50">Baixar</a>
            </li>
          ))}
        </ul>
      </Card>
      <p className="text-xs text-slate-400">Filtros por tipo, linha e produto ainda não estão disponíveis. <Link to="/execucoes" className="underline">Gerar artefato de demonstração</Link></p>
    </div>
  );
}
