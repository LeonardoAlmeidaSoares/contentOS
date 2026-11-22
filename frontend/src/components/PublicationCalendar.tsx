import { useState } from "react";
import { Link } from "react-router-dom";
import { ApprovalItem } from "../api";
import { Icon } from "./StudioVisuals";

const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
export function PublicationCalendar({ items }: { items: ApprovalItem[] }) {
  const [month, setMonth] = useState(
    () => new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  );
  const [selected, setSelected] = useState(() => new Date());
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const start = new Date(first);
  start.setDate(1 - first.getDay());
  const cells =
    Math.ceil(
      (first.getDay() +
        new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()) /
        7,
    ) * 7;
  const monthLabel = month.toLocaleDateString("pt-BR", {
    month: "long",
    year: "numeric",
  });
  const days = Array.from(
    { length: cells },
    (_, i) =>
      new Date(start.getFullYear(), start.getMonth(), start.getDate() + i),
  );
  const events = items.filter((a) => a.publication);
  const forDay = (d: Date) =>
    events.filter(
      (a) => dayKey(new Date(a.publication!.created_at)) === dayKey(d),
    );
  const changeMonth = (delta: number) => {
    const next = new Date(month.getFullYear(), month.getMonth() + delta, 1);
    setMonth(next);
    setSelected(next);
  };
  return (
    <section
      className="studio-card calendar-panel p-4 md:p-5"
      aria-label="Calendário de envios"
    >
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            className="icon-button"
            aria-label="Mês anterior"
            onClick={() => changeMonth(-1)}
          >
            <Icon name="chevron-left" size={17} />
          </button>
          <button
            className="icon-button"
            aria-label="Próximo mês"
            onClick={() => changeMonth(1)}
          >
            <Icon name="chevron-right" size={17} />
          </button>
          <h2 className="ml-1 text-base font-semibold">
            {monthLabel.charAt(0).toUpperCase() + monthLabel.slice(1)}
          </h2>
        </div>
        <button
          className="studio-ghost py-1.5 text-xs"
          onClick={() => {
            const today = new Date();
            setMonth(new Date(today.getFullYear(), today.getMonth(), 1));
            setSelected(today);
          }}
        >
          Hoje
        </button>
      </div>
      <div className="calendar-weekdays">
        {["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"].map((d) => (
          <span key={d}>{d}</span>
        ))}
      </div>
      <div className="calendar-grid">
        {days.map((d) => {
          const daily = forDay(d),
            key = dayKey(d);
          return (
            <button
              type="button"
              key={key}
              className={`calendar-day ${d.getMonth() !== month.getMonth() ? "outside" : ""}`}
              aria-pressed={key === dayKey(selected)}
              aria-label={`${d.toLocaleDateString("pt-BR", { day: "numeric", month: "long", year: "numeric" })}, ${daily.length} envio(s)`}
              onClick={() => setSelected(d)}
            >
              <span className={key === dayKey(new Date()) ? "today" : ""}>
                {d.getDate()}
              </span>
              {daily.length > 0 && (
                <span className="calendar-event-count">
                  {daily.length}
                  <span className="hidden sm:inline">
                    {" "}
                    {daily.length === 1 ? "envio" : "envios"}
                  </span>
                </span>
              )}
            </button>
          );
        })}
      </div>
      <div className="mt-5 border-t border-white/10 pt-5">
        <h3 className="mb-3 text-sm font-semibold">
          {selected.toLocaleDateString("pt-BR", {
            day: "numeric",
            month: "long",
            year: "numeric",
          })}
        </h3>
        {forDay(selected).length === 0 ? (
          <p className="py-4 text-sm text-slate-400">
            Nenhum envio registrado nesta data.
          </p>
        ) : (
          <ul className="space-y-3">
            {forDay(selected).map((a) => (
              <li key={a.run_id}>
                <Link
                  className="flex items-center justify-between gap-3 rounded-lg border border-white/10 p-3 hover:border-cyan-300/40"
                  to={`/aprovacoes/${a.run_id}`}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {a.publication!.title}
                    </span>
                    <span className="mt-1 block text-xs text-slate-400">
                      {a.factory_name} ·{" "}
                      {new Date(a.publication!.created_at).toLocaleTimeString(
                        "pt-BR",
                        { hour: "2-digit", minute: "2-digit" },
                      )}
                    </span>
                  </span>
                  <Icon name="arrow" size={16} className="text-cyan-300" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="mt-4 text-xs leading-relaxed text-slate-500">
        Datas do último envio de cada produção. Esta visualização consulta o
        histórico; o agendamento editorial ainda não está disponível.
      </p>
    </section>
  );
}
