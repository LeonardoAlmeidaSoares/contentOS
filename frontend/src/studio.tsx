import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useLocation } from "react-router-dom";
import { api, Artifact, ChatMsg, ChatReply, Line, PreviewRow, Run, RunSummary, StudioStatus } from "./api";
import { usePoll } from "./hooks";
import { isActiveRun, money } from "./ui";

// ---------- componentes visuais ----------
export const card = "rounded-2xl border border-petrol-700/60 bg-petrol-900/80 shadow-lg shadow-black/20";
export const primary = "rounded-xl bg-cyan-400 px-4 py-2.5 text-sm font-semibold text-petrol-950 transition hover:bg-cyan-300 disabled:opacity-50";
export const ghost = "rounded-xl border border-petrol-600 px-4 py-2.5 text-sm text-slate-200 transition hover:border-cyan-400 hover:text-cyan-300 disabled:opacity-50";
export const input = "w-full rounded-xl border border-petrol-600 bg-petrol-950/70 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none";

const STEP_LABELS: Record<string, string> = {
  script: "Escrevendo o roteiro", scenes: "Dividindo em cenas", images: "Buscando imagens", narration: "Gravando a narração",
  subtitles: "Sincronizando legendas", render: "Montando o vídeo", export: "Validando e exportando",
};
const RUN_LABEL: Record<string, string> = { queued: "Na fila", running: "Produzindo", retrying: "Tentando de novo", succeeded: "Pronto", failed: "Falhou", cancelled: "Cancelada" };

export function Pill({ status }: { status: string }) {
  const c = status === "succeeded" ? "bg-emerald-400/15 text-emerald-300" : status === "failed" ? "bg-red-400/15 text-red-300"
    : status === "cancelled" ? "bg-slate-400/15 text-slate-300" : "bg-cyan-400/15 text-cyan-300";
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${c}`}>{RUN_LABEL[status] ?? status}</span>;
}

function Thumb({ id, className = "" }: { id?: string | null; className?: string }) {
  return id
    ? <img src={api.imageUrl(id)} alt="" className={`aspect-video w-full object-cover ${className}`} />
    : <div className={`flex aspect-video w-full items-center justify-center bg-gradient-to-br from-petrol-800 to-petrol-950 text-3xl ${className}`}>🎬</div>;
}

export function Notice({ tone = "warn", children }: { tone?: "warn" | "error"; children: ReactNode }) {
  return <div className={`rounded-xl border px-4 py-3 text-sm ${tone === "error" ? "border-red-400/40 bg-red-400/10 text-red-200" : "border-amber-400/40 bg-amber-400/10 text-amber-200"}`}>{children}</div>;
}

function useThumbs(): Record<string, string> {
  const { data } = usePoll(() => api.artifacts(), [], 4000);
  const m: Record<string, string> = {};
  (data ?? []).forEach((a: Artifact) => { if (a.filename === "miniatura.jpg") m[a.run_id] = a.id; });
  return m;
}
const useFactories = () => usePoll(async () => (await api.lines()).filter((l) => l.pipeline === "video_youtube"), [], 3000);
const cfgNum = (l: Line, k: string) => Number(l.config[k] ?? 0);
const freqText = (f: number) => (f ? `${f} vídeo(s) por semana` : "Sob demanda");

function SetupNotice({ st }: { st: StudioStatus | null }) {
  if (!st) return null;
  return (
    <div className="space-y-2">
      {!st.gemini.configured && (
        <Notice><strong>Gemini não configurado.</strong> Para criar fábricas e roteiros com IA, crie uma chave gratuita em{" "}
          <a className="underline" href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">aistudio.google.com/apikey</a>,
          adicione <code className="rounded bg-black/30 px-1">GEMINI_API_KEY=sua_chave</code> ao arquivo <code className="rounded bg-black/30 px-1">.env</code> e
          execute <code className="rounded bg-black/30 px-1">docker compose up -d</code>.</Notice>
      )}
      {!st.ffmpeg && <Notice tone="error">FFmpeg não encontrado no servidor: não é possível montar vídeos.</Notice>}
      {st.voice.engines.length === 0 && <Notice tone="error">Nenhuma voz local (Piper/eSpeak) disponível no servidor.</Notice>}
    </div>
  );
}

// ---------- Início ----------
export function Home() {
  const nav = useNavigate();
  const [text, setText] = useState("");
  const { data: st } = usePoll(() => api.studioStatus(), [], 15000);
  const { data: fs } = useFactories();
  const { data: runs } = usePoll(() => api.runs(), [], 3000);
  const thumbs = useThumbs();
  const done = (runs ?? []).filter((r) => r.pipeline === "video_youtube" && r.status === "succeeded").slice(0, 6);
  const go = (e: FormEvent) => { e.preventDefault(); if (text.trim()) nav("/fabricas/nova", { state: { prompt: text.trim() } }); };
  return (
    <div className="space-y-8">
      <section className="rounded-3xl border border-petrol-700/60 bg-gradient-to-br from-petrol-800 via-petrol-900 to-petrol-950 p-8">
        <p className="text-sm font-medium text-cyan-300">ContentOS Studio</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">O que você quer produzir hoje?</h1>
        <p className="mt-2 max-w-xl text-sm text-slate-400">Descreva o canal ou vídeo que você imagina. O estúdio entende, monta a fábrica e produz.</p>
        <form onSubmit={go} className="mt-6 flex flex-col gap-3 sm:flex-row">
          <input value={text} onChange={(e) => setText(e.target.value)} className={input} data-testid="home-prompt"
            placeholder="Ex.: um canal de histórias de terror com vídeos de 10 minutos, 3 vezes por semana…" />
          <button className={primary} data-testid="home-go">Criar Fábrica com IA</button>
        </form>
      </section>
      <SetupNotice st={st ?? null} />
      <section>
        <div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-semibold">Minhas Fábricas</h2><Link to="/fabricas" className="text-sm text-cyan-300 hover:underline">Ver todas</Link></div>
        {fs && fs.length === 0 && <div className={`${card} p-6 text-sm text-slate-400`}>Você ainda não tem fábricas. Descreva uma acima para começar.</div>}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{fs?.slice(0, 3).map((f) => <FactoryCard key={f.id} f={f} thumbs={thumbs} runs={runs ?? []} />)}</div>
      </section>
      {done.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold">Últimos vídeos</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {done.map((r) => <Link key={r.id} to={`/producao/${r.id}`} className={`${card} overflow-hidden hover:border-cyan-400`}><Thumb id={thumbs[r.id]} /><div className="p-3 text-sm"><div className="font-medium">{r.line_name}</div><div className="text-xs text-slate-400">{new Date(r.created_at).toLocaleString("pt-BR")}</div></div></Link>)}
          </div>
        </section>
      )}
    </div>
  );
}

function FactoryCard({ f, thumbs, runs }: { f: Line; thumbs: Record<string, string>; runs: RunSummary[] }) {
  const mine = runs.filter((r) => r.line_id === f.id);
  const last = mine.find((r) => thumbs[r.id]);
  const active = mine.find((r) => isActiveRun(r.status));
  return (
    <Link to={`/fabricas/${f.id}`} data-testid="factory-card" className={`${card} group overflow-hidden transition hover:border-cyan-400`}>
      <div className="relative"><Thumb id={last ? thumbs[last.id] : null} />
        {active && <span className="absolute right-2 top-2 rounded-full bg-cyan-400 px-2 py-0.5 text-xs font-semibold text-petrol-950">Produzindo…</span>}</div>
      <div className="space-y-1 p-4">
        <div className="font-semibold group-hover:text-cyan-300">{f.name}</div>
        <div className="line-clamp-2 text-xs text-slate-400">{f.description}</div>
        <div className="flex flex-wrap gap-x-3 pt-2 text-xs text-slate-400"><span>⏱ {cfgNum(f, "video_minutes")} min</span><span>📅 {freqText(cfgNum(f, "frequency_per_week"))}</span><span>🎞 {f.products} arquivos</span></div>
      </div>
    </Link>
  );
}

// ---------- Minhas Fábricas ----------
export function Factories() {
  const { data: fs, error } = useFactories();
  const { data: runs } = usePoll(() => api.runs(), [], 3000);
  const thumbs = useThumbs();
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between"><h1 className="text-2xl font-semibold">Minhas Fábricas</h1><Link to="/fabricas/nova" className={primary} data-testid="new-factory">+ Criar Fábrica com IA</Link></div>
      {error && <Notice tone="error">Não foi possível carregar as fábricas.</Notice>}
      {fs && fs.length === 0 && <div className={`${card} p-8 text-center text-sm text-slate-400`}>Nenhuma fábrica ainda. Clique em “Criar Fábrica com IA” e descreva o que quer produzir.</div>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{fs?.map((f) => <FactoryCard key={f.id} f={f} thumbs={thumbs} runs={runs ?? []} />)}</div>
    </div>
  );
}

// ---------- Preview de configuração ----------
function PreviewCard({ rows, title }: { rows: PreviewRow[]; title: string }) {
  return (
    <div className={`${card} p-5`} data-testid="proposal">
      <h3 className="mb-3 text-sm font-semibold text-cyan-300">{title}</h3>
      <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">{rows.map((r) => <div key={r.label}><dt className="text-xs text-slate-500">{r.label}</dt><dd className="text-sm">{r.value}</dd></div>)}</dl>
    </div>
  );
}

// ---------- Criar Fábrica com IA ----------
type Turn = ChatMsg & { reply?: ChatReply };
export function CreateFactory() {
  const nav = useNavigate();
  const loc = useLocation();
  const initial = (loc.state as { prompt?: string } | null)?.prompt;
  const { data: st } = usePoll(() => api.studioStatus(), [], 15000);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const lastReply = [...turns].reverse().find((t) => t.reply)?.reply;
  const proposal = lastReply?.status === "ready" ? lastReply.proposal : null;

  const send = async (content: string, base: Turn[]) => {
    const next: Turn[] = [...base, { role: "user", content }];
    setTurns(next); setText(""); setBusy(true); setErr(null);
    try {
      const reply = await api.chat(next.map(({ role, content }) => ({ role, content })));
      const say = [reply.message, ...(reply.status === "need_info" ? reply.questions : [])].filter(Boolean).join("\n\n");
      setTurns([...next, { role: "assistant", content: say, reply }]);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  useEffect(() => { if (initial && !started.current) { started.current = true; void send(initial, []); } }, []); // eslint-disable-line
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [turns, busy]);

  const create = async () => {
    if (!proposal) return;
    setCreating(true);
    try { const r = await api.createFactory(proposal.config); nav(`/fabricas/${r.id}`); } catch (e) { setErr((e as Error).message); setCreating(false); }
  };
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div><h1 className="text-2xl font-semibold">Criar Fábrica com IA</h1><p className="text-sm text-slate-400">Conte o que quer produzir. Eu cuido da configuração.</p></div>
      <SetupNotice st={st ?? null} />
      <div className={`${card} space-y-4 p-5`}>
        {turns.length === 0 && !busy && (
          <div className="space-y-2 text-sm text-slate-400"><p>Exemplo:</p>
            <button className="rounded-xl border border-petrol-600 px-3 py-2 text-left hover:border-cyan-400" onClick={() => setText("Quero criar um canal de histórias de terror com vídeos de dez minutos, três vezes por semana, narração sombria e imagens cinematográficas.")}>
              “Quero criar um canal de histórias de terror com vídeos de dez minutos, três vezes por semana, narração sombria e imagens cinematográficas.”</button></div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={`flex ${t.role === "user" ? "justify-end" : ""}`}>
            <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm ${t.role === "user" ? "bg-cyan-400 text-petrol-950" : "bg-petrol-800 text-slate-100"}`} data-testid={`msg-${t.role}`}>{t.content}</div>
          </div>
        ))}
        {busy && <div className="text-sm text-slate-400" data-testid="thinking">Entendendo seu pedido…</div>}
        {err && <Notice tone="error">{err}</Notice>}
        <div ref={bottom} />
        <form onSubmit={(e) => { e.preventDefault(); if (text.trim() && !busy) void send(text.trim(), turns); }} className="flex gap-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} className={input} data-testid="chat-input"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (text.trim() && !busy) void send(text.trim(), turns); } }}
            placeholder={proposal ? "Quer mudar algo? Escreva aqui (ex.: deixe os vídeos mais curtos)" : "Descreva sua fábrica…"} />
          <button className={primary} disabled={busy || !text.trim()} data-testid="chat-send">Enviar</button>
        </form>
      </div>
      {proposal && (
        <>
          <PreviewCard rows={proposal.preview} title="Prévia da sua fábrica" />
          <div className="flex gap-3"><button className={primary} onClick={create} disabled={creating} data-testid="confirm-create">Confirmar e criar fábrica</button>
            <span className="self-center text-sm text-slate-400">ou continue conversando para ajustar.</span></div>
        </>
      )}
    </div>
  );
}

// ---------- Interior da Fábrica ----------
export function FactoryInside() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const { data: f, error } = usePoll(() => api.factory(id), [id], 60000);
  const [cur, setCur] = useState<{ data: Awaited<ReturnType<typeof api.factory>> } | null>(null);
  const { data: line } = usePoll(() => api.line(id), [id], 3000);
  const { data: runs } = usePoll(() => api.runs(id), [id], 2500);
  const { data: st } = usePoll(() => api.studioStatus(), [], 15000);
  const thumbs = useThumbs();
  const [topic, setTopic] = useState("");
  const [own, setOwn] = useState(false);
  const [script, setScript] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [adj, setAdj] = useState("");
  const [prop, setProp] = useState<ChatReply | null>(null);
  const [adjMsg, setAdjMsg] = useState<string | null>(null);
  const factory = cur?.data ?? f;
  const active = runs?.find((r) => isActiveRun(r.status));

  const produce = async () => {
    setBusy(true); setMsg(null);
    try { const r = await api.produce(id, { topic, script_text: own ? script : "" }); nav(`/producao/${r.id}`); }
    catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  const adjust = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setAdjMsg(null); setProp(null);
    try { setProp(await api.adjustFactory(id, adj)); } catch (x) { setAdjMsg((x as Error).message); } finally { setBusy(false); }
  };
  const apply = async () => {
    if (!prop?.proposal) return;
    const d = await api.applyFactory(id, prop.proposal.config);
    setCur({ data: d }); setProp(null); setAdj(""); setAdjMsg("Ajuste aplicado. Será usado nas próximas produções.");
  };
  const toggleAuto = async () => { await api.lineAction(id, line?.active ? "deactivate" : "activate"); };

  if (error) return <Notice tone="error">Fábrica não encontrada.</Notice>;
  if (!factory || !line) return <p className="text-sm text-slate-400">Carregando…</p>;
  const mine = (runs ?? []).filter((r) => r.pipeline === "video_youtube");
  return (
    <div className="space-y-6">
      <div><Link to="/fabricas" className="text-sm text-cyan-300 hover:underline">← Minhas Fábricas</Link>
        <h1 className="mt-1 text-2xl font-semibold" data-testid="factory-name">{line.name}</h1>
        <Link to={`/canais/${id}`} className="text-sm text-cyan-300 hover:underline" data-testid="open-channel">Abrir Centro do Canal (padrão versionado) →</Link></div>
      <SetupNotice st={st ?? null} />
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          <div className={`${card} space-y-4 p-5`}>
            <h2 className="font-semibold">Produzir um novo vídeo</h2>
            <input value={topic} onChange={(e) => setTopic(e.target.value)} className={input} data-testid="topic"
              placeholder="Tema do vídeo (opcional — se vazio, a IA escolhe um dentro do tema da fábrica)" />
            <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={own} onChange={(e) => setOwn(e.target.checked)} data-testid="own-script" />Tenho meu próprio roteiro (não usa IA)</label>
            {own && <textarea value={script} onChange={(e) => setScript(e.target.value)} rows={6} className={input} data-testid="script-text" placeholder="Cole aqui a narração completa…" />}
            {msg && <Notice tone="error">{msg}</Notice>}
            <div className="flex items-center gap-3">
              <button className={primary} onClick={produce} disabled={busy || !!active || (own && script.trim().length < 20)} data-testid="produce">Produzir vídeo</button>
              {active && <Link className="text-sm text-cyan-300 hover:underline" to={`/producao/${active.id}`}>Há uma produção em andamento →</Link>}
            </div>
            {!own && !st?.gemini.configured && <p className="text-xs text-amber-300">Sem Gemini configurado, só é possível produzir com roteiro próprio.</p>}
          </div>
          <div>
            <h2 className="mb-3 font-semibold">Vídeos desta fábrica</h2>
            {mine.length === 0 && <div className={`${card} p-5 text-sm text-slate-400`}>Nenhuma produção ainda.</div>}
            <div className="grid gap-4 sm:grid-cols-2">
              {mine.map((r) => (
                <Link key={r.id} to={`/producao/${r.id}`} data-testid="video-card" className={`${card} overflow-hidden hover:border-cyan-400`}>
                  <Thumb id={thumbs[r.id]} />
                  <div className="flex items-center justify-between p-3 text-sm"><span className="text-xs text-slate-400">{new Date(r.created_at).toLocaleString("pt-BR")}</span><Pill status={r.status} /></div>
                </Link>))}
            </div>
          </div>
        </div>
        <div className="space-y-6 lg:col-span-2">
          <PreviewCard rows={factory.preview} title="Identidade criativa" />
          <div className={`${card} space-y-3 p-5`}>
            <h2 className="text-sm font-semibold">Ajustar por conversa</h2>
            <form onSubmit={adjust} className="space-y-2">
              <input value={adj} onChange={(e) => setAdj(e.target.value)} className={input} data-testid="adjust-input" placeholder="Ex.: deixe os vídeos com 5 minutos e a voz mais lenta" />
              <button className={ghost} disabled={busy || adj.trim().length < 3} data-testid="adjust-send">Pedir ajuste</button>
            </form>
            {adjMsg && <p className="text-sm text-slate-300" data-testid="adjust-msg">{adjMsg}</p>}
            {prop?.proposal && (<div className="space-y-2"><p className="text-sm text-slate-300">{prop.message}</p>
              <dl className="space-y-1 text-xs">{prop.proposal.preview.map((r) => <div key={r.label} className="flex justify-between gap-3"><dt className="text-slate-500">{r.label}</dt><dd className="text-right">{r.value}</dd></div>)}</dl>
              <div className="flex gap-2"><button className={primary} onClick={apply} data-testid="adjust-apply">Aplicar</button><button className={ghost} onClick={() => setProp(null)}>Descartar</button></div></div>)}
            {prop && !prop.proposal && <p className="text-sm text-amber-200">{[prop.message, ...prop.questions].join(" ")}</p>}
          </div>
          <div className={`${card} space-y-2 p-5 text-sm`}>
            <h2 className="font-semibold">Produção automática</h2>
            <p className="text-xs text-slate-400">{factory.interval_minutes ? `Produz ${freqText(cfgNum(line, "frequency_per_week"))} enquanto estiver ligada.` : "Esta fábrica não tem frequência definida: só produz sob demanda."}</p>
            <button className={ghost} onClick={toggleAuto} disabled={!factory.interval_minutes} data-testid="toggle-auto">{line.active ? "Desligar" : "Ligar"} produção automática</button>
            <p className="text-xs text-slate-500">Custo no mês: {money(line.cost_month)} · Publicação no YouTube ainda não disponível.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------- Visualização da produção ----------
export function Production() {
  const { id = "" } = useParams();
  const { data: run, error } = usePoll(() => api.run(id), [id], 1500, (r: Run) => isActiveRun(r.status) || r.status === "queued");
  const { data: logs } = usePoll(() => api.runLogs(id), [id], 2500, () => !!run && isActiveRun(run.status));
  const [busy, setBusy] = useState(false);
  if (error && !run) return <Notice tone="error">Produção não encontrada.</Notice>;
  if (!run) return <p className="text-sm text-slate-400">Carregando…</p>;
  const art = (n: string) => run.artifacts.find((a) => a.filename === n);
  const video = art("video.mp4");
  const exp = run.steps.find((s) => s.name === "export")?.output as { title?: string; duration_seconds?: number } | null;
  const script = run.steps.find((s) => s.name === "script")?.output as { title?: string } | null;
  const title = exp?.title ?? script?.title ?? "Produção em andamento";
  const act = async (fn: () => Promise<unknown>) => { setBusy(true); try { await fn(); } finally { setBusy(false); } };
  const failed = run.steps.find((s) => s.status === "failed");
  const total = run.steps.length, done = run.steps.filter((s) => s.status === "succeeded").length;
  const warn = (logs ?? []).filter((l) => l.level === "warn");
  return (
    <div className="space-y-6">
      <div><Link to={run.line_id ? `/fabricas/${run.line_id}` : "/fabricas"} className="text-sm text-cyan-300 hover:underline">← {run.line_name ?? "Fábricas"}</Link>
        <div className="mt-1 flex flex-wrap items-center gap-3"><h1 className="text-2xl font-semibold" data-testid="prod-title">{title}</h1><Pill status={run.status} /></div></div>
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-3">
          {video ? (
            <div className={`${card} overflow-hidden`}>
              <video controls preload="metadata" className="aspect-video w-full bg-black" src={api.imageUrl(video.id)} poster={art("miniatura.jpg") ? api.imageUrl(art("miniatura.jpg")!.id) : undefined} data-testid="player" />
              <div className="flex flex-wrap items-center gap-3 p-4">
                <a className={primary} href={api.downloadUrl(video.id)} data-testid="download">Baixar MP4</a>
                {run.pipeline === "video_youtube" && <Link className={ghost} to={`/aprovacoes/${run.id}`} data-testid="go-review">Revisar e aprovar</Link>}
                {art("legendas.srt") && <a className={ghost} href={api.downloadUrl(art("legendas.srt")!.id)}>Baixar legendas (.srt)</a>}
                {art("metadados.json") && <a className={ghost} href={api.downloadUrl(art("metadados.json")!.id)}>Metadados e créditos</a>}
                <span className="text-xs text-slate-400">{exp?.duration_seconds ? `${Math.round(exp.duration_seconds)} s · ` : ""}{(video.size / 1e6).toFixed(1)} MB</span>
              </div>
            </div>
          ) : (
            <div className={`${card} flex aspect-video flex-col items-center justify-center gap-3 p-6 text-center`}>
              {isActiveRun(run.status) ? <><div className="h-10 w-10 animate-spin rounded-full border-4 border-petrol-600 border-t-cyan-400" /><p className="text-sm text-slate-300">{STEP_LABELS[run.steps.find((s) => s.status === "running" || s.status === "retrying")?.name ?? ""] ?? "Preparando…"}</p></>
                : <p className="text-sm text-slate-400">{run.status === "failed" ? "A produção não terminou." : "Sem vídeo."}</p>}
            </div>
          )}
          {run.status === "failed" && <Notice tone="error"><strong>Falhou{failed ? ` em “${STEP_LABELS[failed.name] ?? failed.name}”` : ""}:</strong> {run.error}
            <div className="mt-3"><button className={ghost} disabled={busy} onClick={() => act(() => api.resume(id))} data-testid="resume">Retomar de onde parou</button></div></Notice>}
          {warn.map((l, i) => <Notice key={i}>{l.message}</Notice>)}
        </div>
        <div className="space-y-4 lg:col-span-2">
          <div className={`${card} p-5`}>
            <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">Linha de produção</h2><span className="text-xs text-slate-400">{done}/{total}</span></div>
            <div className="mb-4 h-1.5 overflow-hidden rounded bg-petrol-800"><div className="h-full bg-cyan-400 transition-all" style={{ width: `${(done / total) * 100}%` }} /></div>
            <ol className="space-y-3" data-testid="steps">
              {run.steps.map((s) => (
                <li key={s.name} className="flex gap-3 text-sm">
                  <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs ${s.status === "succeeded" ? "bg-emerald-400 text-petrol-950" : s.status === "failed" ? "bg-red-400 text-petrol-950" : s.status === "running" || s.status === "retrying" ? "animate-pulse bg-cyan-400 text-petrol-950" : "bg-petrol-700 text-slate-400"}`}>
                    {s.status === "succeeded" ? "✓" : s.status === "failed" ? "!" : s.position}</span>
                  <div><div className={s.status === "pending" ? "text-slate-500" : ""}>{STEP_LABELS[s.name] ?? s.name}</div>{s.message && <div className="text-xs text-slate-400">{s.message}</div>}</div>
                </li>))}
            </ol>
            {isActiveRun(run.status) && <button className={`${ghost} mt-4`} disabled={busy} onClick={() => act(() => api.cancel(id))}>Cancelar produção</button>}
          </div>
          <div className={`${card} p-5 text-sm`}><h2 className="mb-2 font-semibold">Custos</h2>
            <p className="text-slate-300" data-testid="cost">{money(run.cost)}</p>
            <p className="text-xs text-slate-500">Narração, imagens livres e montagem são locais/gratuitos. O Gemini é usado só para o roteiro (camada gratuita).</p></div>
        </div>
      </div>
      {logs && logs.length > 0 && <details className={`${card} p-4 text-xs`}><summary className="cursor-pointer text-sm text-slate-300">Registro detalhado</summary>
        <ul className="mt-3 space-y-1 font-mono text-slate-400">{logs.map((l, i) => <li key={i} className={l.level === "error" ? "text-red-300" : l.level === "warn" ? "text-amber-300" : ""}>{new Date(l.created_at).toLocaleTimeString("pt-BR")} {l.step_name ? `[${l.step_name}] ` : ""}{l.message}</li>)}</ul></details>}
    </div>
  );
}
