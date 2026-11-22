import { FormEvent, ReactNode, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { usePoll } from "./hooks";
import { card, ghost, input, Notice, Pill, primary } from "./studio";

type Fmt = { id: "horizontal" | "vertical"; enabled: boolean; min_seconds: number; max_seconds: number };
type Cfg = {
  name: string; channel_name: string; niche: string; theme: string; description: string; audience: string; language: string; platform: string;
  tone: string; narrative_style: string; visual_style: string; editing_rhythm: string; references: string; restrictions: string; forbidden_terms: string[];
  frequency_per_week: number; formats: Fmt[];
  voice: { provider: string | null; voice_id: string | null; language: string; style: string; speed: number; fallback: boolean; description: string; engine: string };
  editing: { subtitles: boolean; ken_burns: boolean; resolution: "720p" | "1080p"; credits: boolean };
} & Record<string, unknown>;
type Std = {
  id: string; version: number; status: "proposed" | "approved" | "rejected" | "superseded"; config: Cfg; preview_rows: { label: string; value: string }[];
  changelog: { field: string; label: string; from: string | null; to: string }[]; pending: string[]; note: string; origin: string;
  preview: { titles: string[]; script_sample: string; visual_direction: string; narration_direction: string } | null; created_at: string; decided_at: string | null; problems: string[];
};
type Check = { name: string; ok: boolean; detail: string };
type RunRow = { id: string; status: string; trigger: string; format: string | null; standard_version: number | null; created_at: string; cost: number; error: string | null; title: string | null; duration_seconds: number | null; validation: { ok: boolean; checks: Check[] } | null; steps_done: number; steps_total: number };
type Channel = { id: string; name: string; legacy: boolean; legacy_config: Cfg | null; current: Std | null; standards: Std[]; runs: RunRow[] };
type Prov = { id: string; label: string; available: boolean; voices: { id: string; label: string }[]; controls: { style: boolean } };
type ChatReply = { status: "need_info" | "ready"; message: string; questions: string[]; proposal: { config: Cfg; assumed: string[] } | null };

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, { method, credentials: "same-origin", headers: body === undefined ? undefined : { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 401) window.dispatchEvent(new Event("unauthorized"));
  if (!res.ok) {
    let d = `HTTP ${res.status}`;
    try { const b = await res.json(); d = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail); } catch { /* sem corpo */ }
    throw new Error(d);
  }
  return res.json();
}
const FMT_LABEL = { horizontal: "Horizontal 16:9", vertical: "Vertical 9:16 (Shorts/Reels)" };
const STATUS = { proposed: "Proposta", approved: "Aprovada (vigente)", rejected: "Rejeitada", superseded: "Substituída" };
const blank = (): Cfg => ({
  name: "", channel_name: "", niche: "", theme: "", description: "", audience: "", language: "pt-BR", platform: "youtube", tone: "", narrative_style: "", visual_style: "",
  editing_rhythm: "medio", references: "", restrictions: "", forbidden_terms: [], frequency_per_week: 0,
  formats: [{ id: "horizontal", enabled: true, min_seconds: 60, max_seconds: 180 }],
  voice: { provider: "piper", voice_id: "faber-medium", language: "pt-BR", style: "", speed: 1, fallback: false, description: "", engine: "piper" },
  editing: { subtitles: true, ken_burns: true, resolution: "720p", credits: true },
});
const normalize = (c: Partial<Cfg>): Cfg => {
  const b = blank();
  return { ...b, ...c, voice: { ...b.voice, ...(c.voice ?? {}), provider: c.voice?.provider ?? c.voice?.engine ?? "piper" }, editing: { ...b.editing, ...(c.editing ?? {}) },
    formats: c.formats?.length ? c.formats : b.formats } as Cfg;
};

function Field({ label, children, hint, assumed }: { label: string; children: ReactNode; hint?: string; assumed?: boolean }) {
  return (
    <label className="block text-sm"><span className="mb-1 flex items-center gap-2 text-slate-300">{label}
      {assumed && <span className="rounded-full bg-amber-400/20 px-2 py-0.5 text-[10px] font-medium text-amber-300">sugerido pela IA — confirme</span>}</span>
      {children}{hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}</label>
  );
}

/** Revisão estruturada do padrão (sem JSON): o usuário corrige tudo antes de aprovar. */
function StandardForm({ initial, assumed = [], submitLabel, onSubmit, busy }: { initial: Partial<Cfg>; assumed?: string[]; submitLabel: string; busy: boolean; onSubmit: (c: Cfg, pending: string[]) => void }) {
  const [c, setC] = useState<Cfg>(() => normalize(initial));
  const [terms, setTerms] = useState((initial.forbidden_terms ?? []).join(", "));
  const [confirmed, setConfirmed] = useState<string[]>([]);
  const { data: prov } = usePoll(() => call<{ providers: Prov[] }>("GET", "/api/voices/providers"), [], 60000);
  const set = <K extends keyof Cfg>(k: K, v: Cfg[K]) => setC((p) => ({ ...p, [k]: v }));
  const setVoice = (k: string, v: unknown) => setC((p) => ({ ...p, voice: { ...p.voice, [k]: v } }));
  const setFmt = (id: Fmt["id"], patch: Partial<Fmt>) => setC((p) => {
    const has = p.formats.some((f) => f.id === id);
    const base: Fmt = { id, enabled: true, min_seconds: id === "vertical" ? 30 : 60, max_seconds: id === "vertical" ? 60 : 180 };
    return { ...p, formats: has ? p.formats.map((f) => (f.id === id ? { ...f, ...patch } : f)) : [...p.formats, { ...base, ...patch }] };
  });
  const provider = prov?.providers.find((p) => p.id === c.voice.provider);
  const open = assumed.filter((a) => !confirmed.includes(a));
  const is = (k: string) => assumed.some((a) => a.toLowerCase().includes(k.toLowerCase())) && !confirmed.includes(k);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit({ ...c, name: c.name || c.channel_name, channel_name: c.channel_name || c.name, theme: c.theme || c.niche, voice: { ...c.voice, language: c.language, fallback: false },
      forbidden_terms: terms.split(",").map((t) => t.trim()).filter(Boolean) }, open);
  };
  const fmt = (id: Fmt["id"]) => c.formats.find((f) => f.id === id);
  return (
    <form onSubmit={submit} className="space-y-6" data-testid="standard-form">
      {assumed.length > 0 && <Notice>A IA sugeriu valores para: <b>{assumed.join(", ")}</b>. Revise; ao aprovar você precisará confirmar essas escolhas.</Notice>}
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Nome da fábrica"><input className={input} value={c.name} onChange={(e) => set("name", e.target.value)} data-testid="f-name" required /></Field>
        <Field label="Nome do canal"><input className={input} value={c.channel_name} onChange={(e) => set("channel_name", e.target.value)} placeholder="igual ao da fábrica se vazio" /></Field>
        <Field label="Nicho" assumed={is("nicho")}><input className={input} value={c.niche} onChange={(e) => set("niche", e.target.value)} data-testid="f-niche" required /></Field>
        <Field label="Público-alvo" assumed={is("público")}><input className={input} value={c.audience} onChange={(e) => set("audience", e.target.value)} /></Field>
        <div className="md:col-span-2"><Field label="Descrição e proposta editorial" assumed={is("descri")}><textarea rows={2} className={input} value={c.description} onChange={(e) => set("description", e.target.value)} /></Field></div>
        <Field label="Idioma principal"><input className={input} value={c.language} onChange={(e) => set("language", e.target.value)} /></Field>
        <Field label="Plataforma principal"><input className={input} value="YouTube" disabled /></Field>
      </div>
      <fieldset className="space-y-3"><legend className="text-sm font-semibold">Formatos e duração</legend>
        {(["horizontal", "vertical"] as const).map((id) => { const f = fmt(id); return (
          <div key={id} className="flex flex-wrap items-center gap-3 rounded-xl border border-petrol-700/60 p-3 text-sm">
            <label className="flex w-64 items-center gap-2"><input type="checkbox" checked={!!f?.enabled} data-testid={`fmt-${id}`} onChange={(e) => setFmt(id, { enabled: e.target.checked })} />{FMT_LABEL[id]}{is("formato") && id === "horizontal" && <span className="text-[10px] text-amber-300">sugerido</span>}</label>
            {f?.enabled && <>
              <label className="flex items-center gap-2">mín. (s)<input type="number" min={10} className={`${input} !w-24 !py-1.5`} value={f.min_seconds} data-testid={`min-${id}`} onChange={(e) => setFmt(id, { min_seconds: Number(e.target.value) })} /></label>
              <label className="flex items-center gap-2">máx. (s)<input type="number" min={10} className={`${input} !w-24 !py-1.5`} value={f.max_seconds} data-testid={`max-${id}`} onChange={(e) => setFmt(id, { max_seconds: Number(e.target.value) })} /></label>
              <span className="text-xs text-slate-500">{(f.min_seconds / 60).toFixed(1)}–{(f.max_seconds / 60).toFixed(1)} min</span></>}
          </div>); })}
      </fieldset>
      <fieldset className="space-y-3"><legend className="text-sm font-semibold">Narração</legend>
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Provedor de voz" assumed={is("voz")}><select className={input} value={c.voice.provider ?? ""} data-testid="f-provider" onChange={(e) => { const p = prov?.providers.find((x) => x.id === e.target.value); setC((q) => ({ ...q, voice: { ...q.voice, provider: e.target.value, voice_id: p?.voices[0]?.id ?? null } })); }}>
            {(prov?.providers ?? []).filter((p) => p.id !== "espeak").map((p) => <option key={p.id} value={p.id} disabled={!p.available}>{p.label}{p.available ? "" : " (indisponível)"}</option>)}</select></Field>
          <Field label="Narrador"><select className={input} value={c.voice.voice_id ?? ""} data-testid="f-voice" onChange={(e) => setVoice("voice_id", e.target.value)}>
            {(provider?.voices ?? []).map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}</select></Field>
          <Field label="Velocidade"><input type="number" step={0.05} min={0.6} max={1.5} className={input} value={c.voice.speed} onChange={(e) => setVoice("speed", Number(e.target.value))} /></Field>
        </div>
        <Field label="Estilo de narração" hint={provider?.controls.style ? "Enviado ao provedor a cada cena." : "Este provedor não controla estilo: o texto é só registro."}>
          <input className={input} value={c.voice.style} onChange={(e) => setVoice("style", e.target.value)} placeholder="ex.: calmo, contido, pausas expressivas" /></Field>
        <p className="text-xs text-slate-500">Sem troca silenciosa: se esta voz estiver indisponível, a produção falha com aviso em vez de usar outra.</p>
      </fieldset>
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Tom" assumed={is("tom")}><input className={input} value={c.tone} onChange={(e) => set("tone", e.target.value)} /></Field>
        <Field label="Estrutura/estilo dos roteiros" assumed={is("narrativo")}><input className={input} value={c.narrative_style} onChange={(e) => set("narrative_style", e.target.value)} /></Field>
        <Field label="Estilo visual" assumed={is("visual")}><input className={input} value={c.visual_style} onChange={(e) => set("visual_style", e.target.value)} /></Field>
        <Field label="Ritmo de edição"><select className={input} value={c.editing_rhythm} onChange={(e) => set("editing_rhythm", e.target.value)}><option value="lento">Lento</option><option value="medio">Médio</option><option value="rapido">Rápido</option></select></Field>
        <Field label="Referências criativas"><input className={input} value={c.references} onChange={(e) => set("references", e.target.value)} /></Field>
        <Field label="Legendas"><select className={input} value={c.editing.subtitles ? "1" : "0"} onChange={(e) => setC((p) => ({ ...p, editing: { ...p.editing, subtitles: e.target.value === "1" } }))}><option value="1">Ligadas</option><option value="0">Desligadas</option></select></Field>
        <Field label="Restrições editoriais" hint="Orientam o roteiro."><textarea rows={2} className={input} value={c.restrictions} onChange={(e) => set("restrictions", e.target.value)} /></Field>
        <Field label="Termos proibidos (separados por vírgula)" hint="Verificados no roteiro: se aparecerem, a produção falha."><input className={input} value={terms} onChange={(e) => setTerms(e.target.value)} data-testid="f-forbidden" /></Field>
      </div>
      {assumed.length > 0 && <div className="flex flex-wrap items-center gap-3 text-sm text-slate-300">Confirmar sugestões:
        {assumed.map((a) => <label key={a} className="flex items-center gap-1"><input type="checkbox" checked={confirmed.includes(a)} onChange={(e) => setConfirmed((p) => (e.target.checked ? [...p, a] : p.filter((x) => x !== a)))} />{a}</label>)}</div>}
      <button className={primary} disabled={busy} data-testid="save-standard">{submitLabel}</button>
    </form>
  );
}

export function NewChannel() {
  const nav = useNavigate();
  const [text, setText] = useState("");
  const [thread, setThread] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [reply, setReply] = useState<ChatReply | null>(null);
  const [manual, setManual] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const send = async (e: FormEvent) => {
    e.preventDefault(); if (!text.trim()) return;
    const msgs = [...thread, { role: "user" as const, content: text.trim() }];
    setBusy(true); setErr(null); setText(""); setThread(msgs);
    try {
      const r = await call<ChatReply>("POST", "/api/studio/chat", { messages: msgs });
      setReply(r); setThread([...msgs, { role: "assistant", content: r.message + (r.questions.length ? "\n" + r.questions.join("\n") : "") }]);
    } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  const save = async (config: Cfg, pending: string[]) => {
    setBusy(true); setErr(null);
    try { const r = await call<{ id: string }>("POST", "/api/studio/channels", { config, pending, origin: reply?.proposal ? "chat" : "manual" }); nav(`/canais/${r.id}`); }
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-semibold">Criar canal</h1>
        <p className="mt-1 text-sm text-slate-400">Descreva o canal; a IA monta uma proposta. Você revisa, corrige e aprova o Padrão do Canal antes de qualquer produção.</p></div>
      <form onSubmit={send} className={`${card} space-y-3 p-5`}>
        {thread.map((m, i) => <p key={i} className={`whitespace-pre-line text-sm ${m.role === "user" ? "text-cyan-200" : "text-slate-300"}`}>{m.role === "user" ? "Você: " : "Assistente: "}{m.content}</p>)}
        <textarea className={input} rows={3} value={text} onChange={(e) => setText(e.target.value)} data-testid="chat-input"
          placeholder="Ex.: canal de histórias de terror, vídeos de 10 minutos, narrador brasileiro, imagens cinematográficas e três publicações por semana às 19h" />
        <div className="flex gap-3"><button className={primary} disabled={busy || !text.trim()} data-testid="chat-send">Interpretar pedido</button>
          {!reply && !manual && <button type="button" className={ghost} onClick={() => setManual(true)}>Preencher manualmente</button>}</div>
      </form>
      {err && <Notice tone="error">{err}</Notice>}
      {(reply?.proposal || manual) && (
        <div className={`${card} p-5`}><h2 className="mb-4 font-semibold">Revisão do padrão proposto</h2>
          <StandardForm key={reply ? JSON.stringify(reply.proposal?.config).length : "m"} initial={reply?.proposal?.config ?? {}} assumed={reply?.proposal?.assumed ?? []} busy={busy} submitLabel="Salvar como proposta (v1)" onSubmit={save} /></div>)}
    </div>
  );
}

function StdCard({ s, ch, reload }: { s: Std; ch: Channel; reload: () => void }) {
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [pf, setPf] = useState(s.config.formats.find((f) => f.enabled)?.id ?? "horizontal");
  const [topic, setTopic] = useState("");
  const act = async (fn: () => Promise<unknown>) => { setBusy(true); setMsg(null); try { await fn(); reload(); } catch (x) { setMsg((x as Error).message); } finally { setBusy(false); } };
  return (
    <div className={`${card} space-y-3 p-5`} data-testid={`std-${s.version}`}>
      <div className="flex items-center justify-between"><h3 className="font-semibold">Versão {s.version}</h3>
        <span className={`rounded-full px-3 py-1 text-xs ${s.status === "approved" ? "bg-emerald-400/20 text-emerald-300" : s.status === "proposed" ? "bg-amber-400/20 text-amber-300" : "bg-slate-500/20 text-slate-400"}`} data-testid="std-status">{STATUS[s.status]}</span></div>
      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">{s.preview_rows.map((r) => <div key={r.label}><dt className="inline text-slate-500">{r.label}: </dt><dd className="inline text-slate-200">{r.value}</dd></div>)}</dl>
      {s.changelog.length > 0 && <div className="rounded-xl bg-petrol-950/60 p-3 text-xs text-slate-300"><b>Alterações desde a versão anterior</b>{s.changelog.map((c) => <p key={c.field}>• {c.label}: {c.from} → <span className="text-cyan-300">{c.to}</span></p>)}</div>}
      {s.problems.length > 0 && <Notice>{s.problems.join(" ")}</Notice>}
      {s.pending.length > 0 && <Notice>Sugestões da IA ainda não confirmadas: {s.pending.join(", ")}.</Notice>}
      {s.preview && <div className="space-y-2 rounded-xl border border-cyan-400/30 p-3 text-sm" data-testid="std-preview"><b className="text-cyan-300">Prévia conceitual</b>
        <p><i>Títulos:</i> {s.preview.titles.join(" · ")}</p><p className="whitespace-pre-line"><i>Abertura do roteiro:</i> {s.preview.script_sample}</p>
        <p><i>Direção visual:</i> {s.preview.visual_direction}</p><p><i>Narração:</i> {s.preview.narration_direction}</p></div>}
      {msg && <Notice tone="error">{msg}</Notice>}
      {(s.status === "proposed" || s.status === "approved") && <div className="flex flex-wrap items-center gap-2">
        {s.status === "proposed" && <>
          {s.pending.length > 0 && <label className="flex items-center gap-1 text-xs text-slate-300"><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />Confirmo as sugestões</label>}
          <button className={primary} disabled={busy || s.problems.length > 0} data-testid="approve" onClick={() => act(() => call("POST", `/api/studio/standards/${s.id}/approve`, { confirm_pending: confirm }))}>Aprovar padrão</button>
          <button className={ghost} disabled={busy} onClick={() => act(() => call("POST", `/api/studio/standards/${s.id}/reject`))}>Rejeitar</button></>}
        <button className={ghost} disabled={busy} data-testid="make-preview" onClick={() => act(() => call("POST", `/api/studio/standards/${s.id}/preview`))}>{busy ? "Gerando…" : "Prévia conceitual"}</button>
        <select className={`${input} !w-auto !py-2`} value={pf} onChange={(e) => setPf(e.target.value as Fmt["id"])}>{s.config.formats.filter((f) => f.enabled).map((f) => <option key={f.id} value={f.id}>{FMT_LABEL[f.id]}</option>)}</select>
        <input className={`${input} !w-56 !py-2`} placeholder="Tema do piloto (opcional)" value={topic} onChange={(e) => setTopic(e.target.value)} />
        <button className={ghost} disabled={busy || ch.runs.some((r) => ["queued", "running", "retrying"].includes(r.status))} data-testid="pilot"
          onClick={() => act(async () => { const r = await call<{ id: string }>("POST", `/api/studio/standards/${s.id}/pilot`, { format: pf, topic }); nav(`/producao/${r.id}`); })}>Solicitar piloto</button>
        <span className="text-xs text-slate-500">O piloto nunca é publicado.</span></div>}
    </div>
  );
}

function Runs({ ch }: { ch: Channel }) {
  const nav = useNavigate();
  const cur = ch.current;
  const fm = cur?.config.formats.filter((f) => f.enabled) ?? [];
  const [fmt, setFmt] = useState<string>("");
  const [topic, setTopic] = useState("");
  const [script, setScript] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (!fmt && fm[0]) setFmt(fm[0].id); }, [fm, fmt]);
  const active = ch.runs.some((r) => ["queued", "running", "retrying"].includes(r.status));
  const go = async () => {
    setBusy(true); setErr(null);
    try { const r = await call<{ id: string }>("POST", `/api/studio/factories/${ch.id}/channel/produce`, { format: fmt, topic, script_text: script }); nav(`/producao/${r.id}`); }
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-6">
      {cur ? (
        <div className={`${card} space-y-3 p-5`}><h2 className="font-semibold">Nova produção — usa o padrão v{cur.version}</h2>
          <div className="flex flex-wrap gap-3"><select className={`${input} !w-auto`} value={fmt} data-testid="p-format" onChange={(e) => setFmt(e.target.value)}>{fm.map((f) => <option key={f.id} value={f.id}>{FMT_LABEL[f.id]} · {f.min_seconds}–{f.max_seconds}s</option>)}</select>
            <input className={`${input} flex-1`} value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Pauta / tema do vídeo (obrigatório nesta etapa)" data-testid="p-topic" /></div>
          <textarea className={input} rows={3} value={script} onChange={(e) => setScript(e.target.value)} placeholder="Roteiro próprio (opcional — se vazio, a IA escreve dentro do padrão)" />
          {err && <Notice tone="error">{err}</Notice>}
          <button className={primary} disabled={busy || active || !topic.trim()} data-testid="p-go" onClick={go}>Produzir vídeo</button>{active && <span className="ml-3 text-xs text-slate-400">Há uma produção em andamento.</span>}</div>
      ) : <Notice>Aprove uma versão do Padrão do Canal (aba Identidade) para liberar a produção.</Notice>}
      <div className="space-y-3">{ch.runs.length === 0 && <div className={`${card} p-5 text-sm text-slate-400`}>Nenhuma produção ainda.</div>}
        {ch.runs.map((r) => (
          <div key={r.id} className={`${card} p-4`} data-testid="run-row">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm"><Link className="text-cyan-300 hover:underline" to={`/producao/${r.id}`}>{r.title ?? "Produção"} · {new Date(r.created_at).toLocaleString("pt-BR")}</Link>
              <span className="flex items-center gap-2"><span className="text-xs text-slate-400">{r.trigger === "pilot" ? "piloto · " : ""}{r.standard_version ? `padrão v${r.standard_version}` : "sem padrão (legado)"}{r.format ? ` · ${r.format === "vertical" ? "9:16" : "16:9"}` : ""}</span><Pill status={r.status} /></span></div>
            {r.validation && <ul className="mt-2 grid gap-1 text-xs sm:grid-cols-2">{r.validation.checks.map((c) => <li key={c.name} className={c.ok ? "text-emerald-300" : "text-red-300"}>{c.ok ? "✔" : "✘"} {c.name}: {c.detail}</li>)}</ul>}
            {r.error && <p className="mt-2 text-xs text-red-300">{r.error}</p>}
          </div>))}</div>
    </div>
  );
}

export function ChannelCenter() {
  const { id = "" } = useParams();
  const { data: ch, error } = usePoll(() => call<Channel>("GET", `/api/studio/factories/${id}/channel`), [id], 3000);
  const [tab, setTab] = useState<"identidade" | "producoes">("identidade");
  const [editing, setEditing] = useState<Partial<Cfg> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [snap, setSnap] = useState<Channel | null>(null);
  useEffect(() => { if (ch) setSnap(ch); }, [ch, tick]);
  const reload = async () => setSnap(await call<Channel>("GET", `/api/studio/factories/${id}/channel`));
  if (error && !snap) return <Notice tone="error">Fábrica não encontrada.</Notice>;
  if (!snap) return <p className="text-sm text-slate-400">Carregando…</p>;
  const c = snap;
  const propose = async (cfg: Cfg, pending: string[]) => {
    setBusy(true); setErr(null);
    try { await call("POST", `/api/studio/factories/${id}/standards`, { config: cfg, pending, origin: "manual" }); setEditing(null); setTick((t) => t + 1); await reload(); }
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  };
  const base = editing ?? null;
  return (
    <div className="space-y-6">
      <div><Link to="/fabricas" className="text-sm text-cyan-300 hover:underline">← Minhas Fábricas</Link><h1 className="mt-1 text-2xl font-semibold" data-testid="channel-name">{c.name}</h1>
        <p className="text-sm text-slate-400">{c.current ? `Padrão vigente: versão ${c.current.version}` : c.legacy ? "Fábrica sem Padrão do Canal versionado (modo anterior)." : "Nenhuma versão aprovada ainda."}</p></div>
      <div className="flex gap-2">{(["identidade", "producoes"] as const).map((t) => <button key={t} className={tab === t ? primary : ghost} onClick={() => setTab(t)} data-testid={`tab-${t}`}>{t === "identidade" ? "Identidade" : "Produções"}</button>)}</div>
      {tab === "producoes" ? <Runs ch={c} /> : (
        <div className="space-y-6">
          {c.legacy && <Notice>Esta fábrica foi criada antes do Padrão do Canal e continua funcionando como antes. Para versionar e aprovar um padrão, crie-o a partir da configuração atual.</Notice>}
          {err && <Notice tone="error">{err}</Notice>}
          {base ? <div className={`${card} p-5`}><h2 className="mb-4 font-semibold">{c.standards.length ? "Propor nova versão" : "Criar Padrão do Canal"}</h2>
            <StandardForm initial={base} busy={busy} submitLabel="Salvar como proposta" onSubmit={propose} /><button className={`${ghost} mt-3`} onClick={() => setEditing(null)}>Cancelar</button></div>
            : <button className={ghost} data-testid="new-version" onClick={() => setEditing(c.standards[0]?.config ?? c.legacy_config ?? {})}>{c.standards.length ? "Propor nova versão" : "Criar Padrão do Canal a partir desta fábrica"}</button>}
          {c.standards.map((s) => <StdCard key={s.id} s={s} ch={c} reload={reload} />)}
        </div>)}
    </div>
  );
}
