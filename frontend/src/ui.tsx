import { ReactNode } from "react";

const colors: Record<string, string> = {
  queued: "bg-slate-100 text-slate-700", retrying: "bg-amber-100 text-amber-700", cancelled: "bg-slate-200 text-slate-600",
  unknown: "bg-slate-100 text-slate-600", error: "bg-red-100 text-red-700", archived: "bg-slate-200 text-slate-600",
  active: "bg-emerald-100 text-emerald-700", inactive: "bg-slate-200 text-slate-600", pending: "bg-slate-100 text-slate-600",
  running: "bg-blue-100 text-blue-700", succeeded: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700", ok: "bg-emerald-100 text-emerald-700",
};
const labels: Record<string, string> = {
  unknown: "Não testado", error: "Com erro", ok: "Disponível", archived: "Arquivada", uncertain: "Incerta",
  queued: "Na fila", retrying: "Nova tentativa", cancelled: "Cancelada", active: "Ativa", inactive: "Inativa", pending: "Pendente", running: "Executando", succeeded: "Concluída", failed: "Falhou",
};

export const Badge = ({ status }: { status: string }) => (
  <span data-testid="status" className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${colors[status] ?? "bg-amber-100 text-amber-700"}`}>
    {labels[status] ?? status}
  </span>
);

export const Card = ({ title, children, action }: { title?: string; children: ReactNode; action?: ReactNode }) => (
  <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
    {(title || action) && (
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-slate-800">{title}</h2>{action}
      </div>
    )}
    {children}
  </section>
);

export const Unavailable = ({ title, text }: { title: string; text: string }) => (
  <div>
    <h1 className="mb-6 text-2xl font-semibold">{title}</h1>
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
      <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-700">Ainda não disponível</span>
      <p className="mx-auto mt-4 max-w-md text-sm text-slate-500">{text}</p>
    </div>
  </div>
);

export const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString("pt-BR") : "—");
export const dur = (a: string | null, b: string | null) =>
  a && b ? `${((new Date(b).getTime() - new Date(a).getTime()) / 1000).toFixed(1)}s` : "—";
export const size = (n: number) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`);

export const money = (n: number | null | undefined) => (n === null || n === undefined ? "—" : `US$ ${Math.abs(n) < 0.1 && n !== 0 ? n.toFixed(4) : n.toFixed(2)}`);
export const isActiveRun = (s: string) => s === "queued" || s === "running" || s === "retrying";

export const Progress = ({ done, total }: { done: number; total: number }) => (
  <div className="flex items-center gap-2" title={`${done}/${total} etapas`}>
    <div className="h-1.5 w-24 overflow-hidden rounded bg-slate-200">
      <div className="h-full bg-blue-600 transition-all" style={{ width: `${total ? (done / total) * 100 : 0}%` }} />
    </div>
    <span className="text-xs text-slate-500">{done}/{total}</span>
  </div>
);

export const btn = "rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50";
export const btnPrimary = "rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50";
