import { ReactNode } from "react";

const colors: Record<string, string> = {
  queued: "bg-slate-100 text-slate-700", pending: "bg-slate-100 text-slate-600",
  running: "bg-blue-100 text-blue-700", succeeded: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700", ok: "bg-emerald-100 text-emerald-700",
};
const labels: Record<string, string> = {
  queued: "Na fila", pending: "Pendente", running: "Executando", succeeded: "Concluída", failed: "Falhou",
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
