import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Line, Pipeline, api } from "../api";
import { Card, btn, btnPrimary } from "../ui";

const field =
  "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm";
const num = (v: string) => (v.trim() === "" ? null : Number(v));

export function LineForm() {
  const { id } = useParams();
  const nav = useNavigate();
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [line, setLine] = useState<Line | null>(null);
  const [f, setF] = useState({
    name: "",
    description: "",
    pipeline: "",
    config: "{}",
    interval: "",
    limRun: "",
    limMonth: "",
    attempts: "3",
    backoff: "5",
  });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) =>
    setF((p) => ({ ...p, [k]: e.target.value }));

  useEffect(() => {
    api
      .pipelines()
      .then((p) => {
        setPipelines(p);
        if (!id && p[0])
          setF((s) => ({
            ...s,
            pipeline: p[0].name,
            config: JSON.stringify(p[0].default_config, null, 2),
          }));
      })
      .catch((x) => setErr((x as Error).message));
    if (id)
      api
        .line(id)
        .then((l) => {
          setLine(l);
          setF({
            name: l.name,
            description: l.description,
            pipeline: l.pipeline,
            config: JSON.stringify(l.config, null, 2),
            interval: l.interval_minutes?.toString() ?? "",
            limRun: l.cost_limit_run?.toString() ?? "",
            limMonth: l.cost_limit_month?.toString() ?? "",
            attempts: String(l.max_attempts),
            backoff: String(l.backoff_seconds),
          });
        })
        .catch((x) => setErr((x as Error).message));
  }, [id]);

  const pickPipeline = (name: string) => {
    const p = pipelines.find((x) => x.name === name);
    setF((s) => ({
      ...s,
      pipeline: name,
      config: JSON.stringify(p?.default_config ?? {}, null, 2),
    }));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    let config: Record<string, unknown>;
    try {
      config = JSON.parse(f.config);
      if (
        typeof config !== "object" ||
        config === null ||
        Array.isArray(config)
      )
        throw 0;
    } catch {
      return setErr("Configuração deve ser um objeto JSON válido.");
    }
    const body = {
      name: f.name,
      description: f.description,
      pipeline: f.pipeline,
      config,
      interval_minutes: num(f.interval),
      cost_limit_run: num(f.limRun),
      cost_limit_month: num(f.limMonth),
      max_attempts: Number(f.attempts),
      backoff_seconds: Number(f.backoff),
    };
    try {
      const saved = id
        ? await api.updateLine(id, body)
        : await api.createLine(body);
      nav(`/linhas/${saved.id}`);
    } catch (x) {
      setErr((x as Error).message);
    }
  };

  const p = pipelines.find((x) => x.name === f.pipeline);
  if (!pipelines.length || (id && !line))
    return err ? (
      <p role="alert" className="text-sm text-red-300">
        Não foi possível carregar a configuração: {err}
      </p>
    ) : (
      <p role="status" className="text-sm text-slate-400">
        Carregando configuração…
      </p>
    );
  return (
    <form onSubmit={submit} className="space-y-6">
      <div>
        <Link
          to={id ? `/linhas/${id}` : "/linhas"}
          className="text-sm text-blue-600 hover:underline"
        >
          ← Voltar
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">
          {id ? `Editar ${line?.name ?? ""}` : "Nova linha de produção"}
        </h1>
      </div>
      <Card title="Geral">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm">
            Nome
            <input
              required
              className={field}
              value={f.name}
              onChange={set("name")}
              data-testid="f-name"
            />
          </label>
          <label className="text-sm">
            Tipo de pipeline
            <select
              className={field}
              value={f.pipeline}
              disabled={!!id}
              onChange={(e) => pickPipeline(e.target.value)}
            >
              {pipelines.map((x) => (
                <option key={x.name} value={x.name}>
                  {x.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm sm:col-span-2">
            Descrição
            <input
              className={field}
              value={f.description}
              onChange={set("description")}
            />
          </label>
        </div>
        {p && (
          <p className="mt-3 text-xs text-slate-500">
            {p.description} Etapas: {p.steps.join(" → ")}
          </p>
        )}
      </Card>
      <Card title="Configuração do pipeline (JSON)">
        <textarea
          className={`${field} h-48 font-mono text-xs`}
          value={f.config}
          onChange={set("config")}
          data-testid="f-config"
        />
      </Card>
      <Card title="Agendamento, orçamento e retry">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm">
            Frequência (minutos; vazio = só manual)
            <input
              type="number"
              min={1}
              className={field}
              value={f.interval}
              onChange={set("interval")}
              data-testid="f-interval"
            />
          </label>
          <span />
          <label className="text-sm">
            Limite de custo por execução (US$)
            <input
              type="number"
              step="any"
              min={0}
              className={field}
              value={f.limRun}
              onChange={set("limRun")}
              data-testid="f-limrun"
            />
          </label>
          <label className="text-sm">
            Limite de custo mensal (US$)
            <input
              type="number"
              step="any"
              min={0}
              className={field}
              value={f.limMonth}
              onChange={set("limMonth")}
              data-testid="f-limmonth"
            />
          </label>
          <label className="text-sm">
            Tentativas por etapa
            <input
              type="number"
              min={1}
              max={10}
              className={field}
              value={f.attempts}
              onChange={set("attempts")}
            />
          </label>
          <label className="text-sm">
            Backoff inicial (s, dobra a cada tentativa)
            <input
              type="number"
              min={0}
              className={field}
              value={f.backoff}
              onChange={set("backoff")}
            />
          </label>
        </div>
      </Card>
      {err && (
        <p className="text-sm text-red-600" data-testid="form-error">
          {err}
        </p>
      )}
      <div className="flex gap-3">
        <button className={btnPrimary} data-testid="save-line">
          Salvar
        </button>
        <Link to={id ? `/linhas/${id}` : "/linhas"} className={btn}>
          Cancelar
        </Link>
      </div>
    </form>
  );
}
