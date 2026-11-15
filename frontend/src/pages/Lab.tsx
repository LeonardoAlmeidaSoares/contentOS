import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { BenchEstimate, BenchPrompt, Estimate, LabRequest, LabResult, Provider, Target, api } from "../api";
import { TargetPicker, selectedModels } from "../components/TargetPicker";
import { usePoll } from "../hooks";
import { Badge, Card, btn, btnPrimary, fmt, money } from "../ui";

const field = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm";
const RATIOS = ["1:1", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9", "4:5", "5:4"];

export function LabLayout() {
  const tabs = [["imagens", "Imagens"], ["texto", "Texto"], ["benchmark", "Benchmark"], ["experimentos", "Histórico"]];
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Laboratório</h1>
      <nav className="flex flex-wrap gap-2 border-b border-slate-200 pb-3">
        {tabs.map(([to, label]) => (
          <NavLink key={to} to={`/laboratorio/${to}`} className={({ isActive }) => `rounded-lg px-3 py-1.5 text-sm ${isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}>{label}</NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}

function useProviders() {
  const { data } = usePoll(api.providers, [], 10000);
  return data ?? ([] as Provider[]);
}

function EstimateBox({ est, allow, setAllow }: { est: Estimate | null; allow: boolean; setAllow: (b: boolean) => void }) {
  if (!est) return <p className="text-sm text-slate-400">A estimativa de custo aparece após preencher o prompt e escolher modelos.</p>;
  return (
    <div className="space-y-2 text-sm" data-testid="estimate">
      <ul className="space-y-1">
        {est.targets.map((t) => (
          <li key={t.provider_id + t.model} className="flex flex-wrap justify-between gap-2">
            <span>{t.provider_name} · <span className="font-mono text-xs">{t.model}</span></span>
            <span className={t.error ? "text-red-600" : t.cost === null ? "text-amber-700" : ""}>
              {t.error ? t.error : t.cost === null ? `custo desconhecido (${t.basis})` : `${money(t.cost)} — ${t.basis}`}</span>
          </li>
        ))}
      </ul>
      <div className="flex justify-between border-t border-slate-100 pt-2 font-medium"><span>Total estimado</span><span data-testid="estimate-total">{money(est.total_known)}</span></div>
      <p className="text-xs text-slate-500">Orçamento mensal do Laboratório: {money(est.lab_month_spent)} / {money(est.lab_month_limit)}. Valores efetivos são conciliados após a execução.</p>
      {est.has_unknown && <label className="flex items-start gap-2 text-amber-800"><input type="checkbox" checked={allow} onChange={(e) => setAllow(e.target.checked)} data-testid="allow-unknown" />
        Autorizo executar mesmo com custo não determinável previamente (o provedor poderá cobrar valor não estimado).</label>}
    </div>
  );
}

function useEstimate(req: LabRequest | null) {
  const [est, setEst] = useState<Estimate | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const key = JSON.stringify(req);
  useEffect(() => {
    if (!req) { setEst(null); setErr(null); return; }
    const t = setTimeout(() => api.labEstimate(req).then((e) => { setEst(e); setErr(null); }).catch((x) => { setEst(null); setErr((x as Error).message); }), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return { est, err };
}

export function LabImages() {
  const nav = useNavigate();
  const providers = useProviders();
  const [prompt, setPrompt] = useState("");
  const [neg, setNeg] = useState("");
  const [targets, setTargets] = useState<Target[]>([]);
  const [ratio, setRatio] = useState("1:1");
  const [res, setRes] = useState("1K");
  const [quality, setQuality] = useState("medium");
  const [n, setN] = useState(1);
  const [refs, setRefs] = useState<string[]>([]);
  const [allow, setAllow] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const models = selectedModels(providers, targets);
  const sup = (k: "aspect_ratios" | "qualities" | "resolutions") => Array.from(new Set(models.flatMap((m) => m.supports?.[k] ?? [])));
  const ratios = sup("aspect_ratios").length ? RATIOS.filter((r) => sup("aspect_ratios").includes(r)) : RATIOS;
  const supportsNeg = models.some((m) => m.supports?.negative_prompt);
  const supportsRef = models.some((m) => m.supports?.reference_images);
  const req: LabRequest | null = prompt.trim() && targets.length
    ? { kind: "image", prompt, negative_prompt: supportsNeg && neg ? neg : null, targets, aspect_ratio: ratio, resolution: res, quality, n, max_tokens: 1024, references: supportsRef ? refs : [], allow_unknown_cost: allow } : null;
  const { est, err: estErr } = useEstimate(req);

  const submit = async () => {
    if (!req) return;
    setErr(null);
    try { nav(`/laboratorio/experimentos/${(await api.labCreate(req)).id}`); } catch (e) { setErr((e as Error).message); }
  };
  const blocked = !req || !est || est.has_error || (est.has_unknown && !allow);
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4">
        <Card title="Prompt">
          <textarea className={`${field} h-32`} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Descreva a ilustração…" data-testid="lab-prompt" />
          {supportsNeg && <label className="mt-3 block text-sm">Prompt negativo<textarea className={`${field} h-16`} value={neg} onChange={(e) => setNeg(e.target.value)} /></label>}
          {models.length > 0 && !supportsNeg && <p className="mt-2 text-xs text-slate-400">Prompt negativo não é suportado pelos modelos selecionados — descreva exclusões no próprio prompt.</p>}
        </Card>
        <Card title="Modelos (selecione vários para comparar)"><TargetPicker kind="image" providers={providers} value={targets} onChange={setTargets} /></Card>
        <Card title="Parâmetros">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <label>Proporção<select className={field} value={ratio} onChange={(e) => setRatio(e.target.value)}>{ratios.map((r) => <option key={r}>{r}</option>)}</select></label>
            <label>Resolução<select className={field} value={res} onChange={(e) => setRes(e.target.value)}>{(sup("resolutions").length ? sup("resolutions") : ["1K"]).map((r) => <option key={r}>{r}</option>)}</select></label>
            <label>Qualidade<select className={field} value={quality} onChange={(e) => setQuality(e.target.value)}>{(sup("qualities").length ? sup("qualities") : ["standard"]).map((r) => <option key={r}>{r}</option>)}</select></label>
            <label>Quantidade<input type="number" min={1} max={10} className={field} value={n} onChange={(e) => setN(Number(e.target.value) || 1)} /></label>
          </div>
          {supportsRef && (
            <div className="mt-3 text-sm">Imagens de referência
              <input type="file" accept="image/png,image/jpeg,image/webp" multiple className="mt-1 block text-xs"
                onChange={async (e) => { const keys: string[] = []; for (const f of Array.from(e.target.files ?? [])) keys.push((await api.uploadRef(f)).key); setRefs(keys); }} />
              {refs.length > 0 && <span className="text-xs text-slate-500">{refs.length} enviada(s)</span>}</div>
          )}
        </Card>
      </div>
      <div className="space-y-4">
        <Card title="Estimativa de custo">
          <EstimateBox est={est} allow={allow} setAllow={setAllow} />
          {estErr && <p className="mt-2 text-sm text-red-600">{estErr}</p>}
        </Card>
        {err && <p className="text-sm text-red-600" data-testid="lab-error">{err}</p>}
        <button className={btnPrimary} disabled={blocked} onClick={submit} data-testid="lab-run">Gerar {targets.length > 1 ? `em ${targets.length} modelos` : ""}</button>
      </div>
    </div>
  );
}

export function LabText() {
  const nav = useNavigate();
  const providers = useProviders();
  const [prompt, setPrompt] = useState("");
  const [system, setSystem] = useState("");
  const [maxTokens, setMaxTokens] = useState(512);
  const [targets, setTargets] = useState<Target[]>([]);
  const [allow, setAllow] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const req: LabRequest | null = prompt.trim() && targets.length
    ? { kind: "text", prompt, system: system || null, targets, aspect_ratio: "1:1", resolution: "1K", quality: "medium", n: 1, max_tokens: maxTokens, references: [], allow_unknown_cost: allow } : null;
  const { est, err: estErr } = useEstimate(req);
  const submit = async () => { if (!req) return; setErr(null); try { nav(`/laboratorio/experimentos/${(await api.labCreate(req)).id}`); } catch (e) { setErr((e as Error).message); } };
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4">
        <Card title="Prompt">
          <label className="text-sm">Instruções do sistema (opcional)<input className={field} value={system} onChange={(e) => setSystem(e.target.value)} /></label>
          <textarea className={`${field} mt-3 h-40`} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Escreva o prompt…" data-testid="lab-prompt" />
          <label className="mt-3 block text-sm">Máximo de tokens de saída (limita o custo)<input type="number" min={16} max={16000} className={field} value={maxTokens} onChange={(e) => setMaxTokens(Number(e.target.value) || 16)} /></label>
        </Card>
        <Card title="Modelos"><TargetPicker kind="text" providers={providers} value={targets} onChange={setTargets} /></Card>
      </div>
      <div className="space-y-4">
        <Card title="Estimativa de custo (teto)"><EstimateBox est={est} allow={allow} setAllow={setAllow} />{estErr && <p className="mt-2 text-sm text-red-600">{estErr}</p>}</Card>
        {err && <p className="text-sm text-red-600" data-testid="lab-error">{err}</p>}
        <button className={btnPrimary} disabled={!req || !est || est.has_error || (est.has_unknown && !allow)} onClick={submit} data-testid="lab-run">Executar</button>
      </div>
    </div>
  );
}

function ResultCard({ r, kind, onSaved }: { r: LabResult; kind: string; onSaved: () => void }) {
  const [rating, setRating] = useState<number | null>(r.rating);
  const [notes, setNotes] = useState(r.notes);
  const [saved, setSaved] = useState(false);
  const save = async (rt: number | null, nt: string) => { await api.rate(r.id, { rating: rt, notes: nt }); setSaved(true); onSaved(); setTimeout(() => setSaved(false), 1500); };
  const active = ["queued", "running", "retrying"].includes(r.status);
  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm" data-testid="result-card">
      <div className="flex items-start justify-between gap-2">
        <div><div className="font-mono text-sm" data-testid="result-model">{r.model}</div><div className="text-xs text-slate-500">{r.provider_name}</div></div>
        <Badge status={r.status} />
      </div>
      {active && <p className="text-sm text-slate-500">Gerando em background…</p>}
      {r.error && <p className="text-sm text-red-600" data-testid="result-error">{r.error}</p>}
      {r.images.map((im) => (
        <div key={im.artifact_id} className="space-y-1">
          <img src={api.imageUrl(im.artifact_id)} alt={im.filename} className="w-full rounded-lg border border-slate-200 bg-white object-contain" data-testid="result-image" />
          <div className="flex items-center justify-between text-xs text-slate-500"><span>{im.width && im.height ? `${im.width}×${im.height}` : "—"}</span>
            <a className="text-blue-600 hover:underline" href={api.downloadUrl(im.artifact_id)} data-testid="result-download">Baixar</a></div>
        </div>
      ))}
      {kind === "text" && r.text && <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-sm" data-testid="result-text">{r.text}</pre>}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-600">
        <div><dt className="text-slate-400">Tempo</dt><dd>{r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : "—"}</dd></div>
        <div><dt className="text-slate-400">Custo</dt><dd data-testid="result-cost">{money(r.cost_effective)} <span className="text-slate-400">({r.cost_source ?? "—"}{r.cost_unknown ? ", sem estimativa" : ""})</span></dd></div>
        <div><dt className="text-slate-400">Estimado</dt><dd>{money(r.cost_estimated)}</dd></div>
        <div><dt className="text-slate-400">Tokens (ent/saí)</dt><dd>{r.input_tokens ?? "—"} / {r.output_tokens ?? "—"}</dd></div>
      </dl>
      <div className="border-t border-slate-100 pt-3">
        <div className="flex items-center gap-1" role="radiogroup" aria-label="Nota">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" data-testid={`rate-${n}`} onClick={() => { setRating(n); save(n, notes); }}
              className={`h-8 w-8 rounded-lg border text-sm ${rating === n ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 hover:bg-slate-50"}`}>{n}</button>
          ))}
          {saved && <span className="ml-2 text-xs text-emerald-600">salvo</span>}
        </div>
        <textarea className={`${field} h-14 text-xs`} value={notes} placeholder="Observações de qualidade…" onChange={(e) => setNotes(e.target.value)} onBlur={() => notes !== r.notes && save(rating, notes)} data-testid="result-notes" />
      </div>
    </div>
  );
}

export function ExperimentView() {
  const { id = "" } = useParams();
  const [tick, setTick] = useState(0);
  const { data: e, error } = usePoll(() => api.experiment(id), [id, tick], 1500, (x) => x.results.some((r) => ["queued", "running", "retrying"].includes(r.status)));
  if (error && !e) return <p className="text-sm text-red-600">Experimento não encontrado.</p>;
  if (!e) return <p className="text-sm text-slate-500">Carregando…</p>;
  const cols = e.results.length >= 3 ? "lg:grid-cols-3" : e.results.length === 2 ? "sm:grid-cols-2" : "";
  return (
    <div className="space-y-4">
      <Link to="/laboratorio/experimentos" className="text-sm text-blue-600 hover:underline">← Histórico</Link>
      <Card title={`${e.kind === "image" ? "Imagens" : "Texto"}${e.label ? ` — ${e.label}` : ""} · ${fmt(e.created_at)}`}>
        <p className="whitespace-pre-wrap text-sm" data-testid="exp-prompt">{e.prompt}</p>
        {e.negative_prompt && <p className="mt-2 text-xs text-slate-500">Negativo: {e.negative_prompt}</p>}
        <p className="mt-2 text-xs text-slate-500">{e.kind === "image" ? `${e.params.aspect_ratio} · ${e.params.resolution} · qualidade ${e.params.quality} · n=${e.params.n}` : `max ${e.params.max_tokens} tokens`} · custo total {money(e.total_cost)}</p>
      </Card>
      <div className={`grid gap-4 ${cols}`}>{e.results.map((r) => <ResultCard key={r.id} r={r} kind={e.kind} onSaved={() => setTick((t) => t + 1)} />)}</div>
    </div>
  );
}

export function LabHistory() {
  const { data } = usePoll(api.experiments, [], 4000);
  return (
    <Card>
      {data && data.length === 0 && <p className="text-sm text-slate-500">Nenhum experimento ainda.</p>}
      <ul className="divide-y divide-slate-100">
        {data?.map((e) => (
          <li key={e.id}><Link to={`/laboratorio/experimentos/${e.id}`} data-testid="exp-row" className="block py-3 text-sm hover:bg-slate-50">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span><span className="mr-2 rounded bg-slate-100 px-2 py-0.5 text-xs">{e.kind === "image" ? "imagem" : "texto"}</span>{e.label ?? e.prompt.slice(0, 70)}</span>
              <span className="text-xs text-slate-400">{fmt(e.created_at)}</span></div>
            <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
              {e.results.map((r) => <span key={r.id} className="rounded border border-slate-200 px-2 py-0.5">{r.model} · {r.status === "succeeded" ? "ok" : r.status}{r.rating ? ` · ★${r.rating}` : ""} · {money(r.cost_effective)}</span>)}
            </div></Link></li>
        ))}
      </ul>
    </Card>
  );
}

export function LabBenchmark() {
  const nav = useNavigate();
  const providers = useProviders();
  const [prompts, setPrompts] = useState<BenchPrompt[]>([]);
  const [targets, setTargets] = useState<Target[]>([]);
  const [ratio, setRatio] = useState("3:4");
  const [res, setRes] = useState("1K");
  const [quality, setQuality] = useState("medium");
  const [est, setEst] = useState<BenchEstimate | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [allow, setAllow] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.benchPrompts().then(setPrompts); }, []);
  const params = useMemo(() => ({ targets, aspect_ratio: ratio, resolution: res, quality, n: 1, max_tokens: 1024, references: [], allow_unknown_cost: allow }), [targets, ratio, res, quality, allow]);
  useEffect(() => {
    setConfirm(false);
    if (!targets.length) { setEst(null); return; }
    const t = setTimeout(() => api.benchEstimate(params).then((e) => { setEst(e); setErr(null); }).catch((x) => { setEst(null); setErr((x as Error).message); }), 350);
    return () => clearTimeout(t);
  }, [params, targets.length]);
  const run = async () => {
    if (!est) return;
    setErr(null);
    try { await api.benchRun({ ...params, confirm_total_usd: est.total_known }); nav("/laboratorio/experimentos"); } catch (e) { setErr((e as Error).message); }
  };
  const models = selectedModels(providers, targets);
  const ratios = Array.from(new Set(models.flatMap((m) => m.supports?.aspect_ratios ?? [])));
  const qualities = Array.from(new Set(models.flatMap((m) => m.supports?.qualities ?? [])));
  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        Benchmark de livros de colorir preparado para execução pelo Product Owner. <strong>Nada é executado automaticamente</strong>:
        a execução exige selecionar os modelos e confirmar o gasto estimado.
      </div>
      <Card title={`Prompts de referência (${prompts.length} categorias)`}>
        <ul className="space-y-2">
          {prompts.map((p) => (
            <li key={p.id}><details data-testid="bench-prompt"><summary className="cursor-pointer text-sm font-medium">{p.category}</summary>
              <p className="mt-2 text-xs text-slate-600">{p.prompt}</p><p className="mt-1 text-xs text-slate-400">Negativo: {p.negative_prompt}</p></details></li>
          ))}
        </ul>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <Card title="Modelos a comparar"><TargetPicker kind="image" providers={providers} value={targets} onChange={setTargets} /></Card>
          <Card title="Parâmetros">
            <div className="grid grid-cols-3 gap-3 text-sm">
              <label>Proporção<select className={field} value={ratio} onChange={(e) => setRatio(e.target.value)}>{(ratios.length ? RATIOS.filter((r) => ratios.includes(r)) : RATIOS).map((r) => <option key={r}>{r}</option>)}</select></label>
              <label>Resolução<input className={field} value={res} onChange={(e) => setRes(e.target.value)} /></label>
              <label>Qualidade<select className={field} value={quality} onChange={(e) => setQuality(e.target.value)}>{(qualities.length ? qualities : ["medium"]).map((r) => <option key={r}>{r}</option>)}</select></label>
            </div>
          </Card>
        </div>
        <Card title="Estimativa total">
          {!est ? <p className="text-sm text-slate-400">Selecione modelos para estimar ({prompts.length} prompts × modelos).</p> : (
            <div className="space-y-2 text-sm" data-testid="bench-estimate">
              <p>{est.generations} gerações ({est.prompts} prompts × {targets.length} modelos)</p>
              <ul>{est.targets.map((t) => <li key={t.provider_name + t.model} className="flex justify-between"><span className="font-mono text-xs">{t.model}</span>
                <span className={t.error ? "text-red-600" : t.unknown ? "text-amber-700" : ""}>{t.error ?? (t.unknown ? "custo desconhecido" : money(t.cost))}</span></li>)}</ul>
              <div className="flex justify-between border-t border-slate-100 pt-2 font-medium"><span>Total estimado</span><span data-testid="bench-total">{money(est.total_known)}</span></div>
              <p className="text-xs text-slate-500">Orçamento mensal do Laboratório: {money(est.lab_month_spent)} / {money(est.lab_month_limit)}</p>
              {est.has_unknown && <label className="flex items-start gap-2 text-amber-800"><input type="checkbox" checked={allow} onChange={(e) => setAllow(e.target.checked)} />Autorizo custo não determinável previamente.</label>}
              <label className="flex items-start gap-2"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} data-testid="bench-confirm" />Confirmo o gasto estimado de {money(est.total_known)}.</label>
            </div>
          )}
          {err && <p className="mt-2 text-sm text-red-600" data-testid="bench-error">{err}</p>}
          <button className={`${btnPrimary} mt-4`} disabled={!est || !confirm || est.has_error || (est.has_unknown && !allow)} onClick={run} data-testid="bench-run">Executar benchmark</button>
        </Card>
      </div>
    </div>
  );
}
