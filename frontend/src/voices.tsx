import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, Line } from "./api";
import { usePoll } from "./hooks";
import { card, ghost, input, Notice, primary } from "./studio";

type VoiceInfo = { id: string; label: string; gender: string | null; note: string };
type Provider = {
  id: string; label: string; kind: "local" | "cloud"; available: boolean; reason: string; requirements: string; cost: string; limits: string;
  quality_note: string; controls: { speed: [number, number] | null; style: boolean; pitch: [number, number] | null }; voices: VoiceInfo[];
};
type Sample = { id: string; provider: string; voice: string; text: string; params: { speed?: number; style?: string; pitch?: number }; seconds: number; gen_ms: number; cost: number; created_at: string; audio_url: string };
type Interp = { provider: string; voice: string; speed: number | null; style: string; explanation: string; unsupported: string[]; instruction: string };
type Identity = { voice: Record<string, unknown>; provider: string; voice_id: string | null; legacy: boolean };

async function vcall<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, { method, credentials: "same-origin", headers: body === undefined ? undefined : { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 401) window.dispatchEvent(new Event("unauthorized"));
  if (!res.ok) {
    let d = `HTTP ${res.status}`;
    try { const b = await res.json(); d = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail); } catch { /* sem corpo */ }
    throw new Error(d);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}
const vapi = {
  providers: () => vcall<{ providers: Provider[]; default_text: string; max_chars: number }>("GET", "/api/voices/providers"),
  samples: () => vcall<Sample[]>("GET", "/api/voices/samples"),
  make: (b: object) => vcall<Sample>("POST", "/api/voices/samples", b),
  del: (id: string) => vcall<void>("DELETE", `/api/voices/samples/${id}`),
  interpret: (instruction: string) => vcall<Interp>("POST", "/api/voices/interpret", { instruction }),
  identity: (lid: string) => vcall<Identity>("GET", `/api/voices/factories/${lid}`),
  save: (lid: string, b: object) => vcall<Identity>("PUT", `/api/voices/factories/${lid}`, b),
};

export function VoiceLab() {
  const [qs] = useSearchParams();
  const { data: cat, error: catErr } = usePoll(() => vapi.providers(), [], 20000);
  const { data: samples } = usePoll(() => vapi.samples(), [], 20000);
  const [list, setList] = useState<Sample[] | null>(null);
  const { data: lines } = usePoll(async () => (await api.lines()).filter((l: Line) => l.pipeline === "video_youtube"), [], 15000);
  const [fid, setFid] = useState(qs.get("fabrica") ?? "");
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [text, setText] = useState("");
  const [provider, setProvider] = useState("");
  const [voice, setVoice] = useState("");
  const [speed, setSpeed] = useState(1);
  const [style, setStyle] = useState("");
  const [nl, setNl] = useState("");
  const [interp, setInterp] = useState<Interp | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "warn" | "error"; text: string } | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  useEffect(() => { if (samples) setList((cur) => cur ?? samples); }, [samples]);
  useEffect(() => { if (cat && !text) setText(cat.default_text); }, [cat]); // eslint-disable-line
  useEffect(() => {
    if (cat && !provider) { const p = cat.providers.find((x) => x.available) ?? cat.providers[0]; if (p) pick(p.id); }
  }, [cat]); // eslint-disable-line
  useEffect(() => { setIdentity(null); if (fid) vapi.identity(fid).then(setIdentity).catch(() => setIdentity(null)); }, [fid]);

  const cur = cat?.providers.find((p) => p.id === provider);
  const pick = (id: string, v?: string) => {
    const p = cat?.providers.find((x) => x.id === id);
    setProvider(id); setVoice(v && p?.voices.some((x) => x.id === v) ? v : p?.voices[0]?.id ?? "");
  };

  const generate = async () => {
    setBusy("gen"); setMsg(null); setOk(null);
    try {
      const s = await vapi.make({ provider, voice, text, speed: cur?.controls.speed ? speed : null, style: cur?.controls.style ? style : "" });
      setList([s, ...(list ?? [])]);
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); } finally { setBusy(null); }
  };
  const interpret = async () => {
    setBusy("nl"); setMsg(null); setInterp(null);
    try {
      const r = await vapi.interpret(nl);
      setInterp(r); pick(r.provider, r.voice); if (r.speed) setSpeed(r.speed); setStyle(r.style);
    } catch (e) { setMsg({ tone: "warn", text: (e as Error).message }); } finally { setBusy(null); }
  };
  const useSample = async (s: Sample) => {
    setBusy(s.id); setMsg(null); setOk(null);
    try {
      const r = await vapi.save(fid, { provider: s.provider, voice_id: s.voice, speed: s.params.speed ?? 1, pitch: s.params.pitch ?? 40, style: s.params.style ?? "", instructions: interp?.instruction ?? nl });
      setIdentity(r); setOk("Voz salva na fábrica. Será usada nas próximas produções.");
    } catch (e) { setMsg({ tone: "error", text: (e as Error).message }); } finally { setBusy(null); }
  };
  const remove = async (id: string) => { await vapi.del(id); setList((list ?? []).filter((s) => s.id !== id)); };

  if (catErr) return <Notice tone="error">Não foi possível carregar os provedores de voz.</Notice>;
  if (!cat) return <p className="text-sm text-slate-400">Carregando…</p>;
  const fname = lines?.find((l) => l.id === fid)?.name;
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-semibold">Laboratório de Vozes</h1>
        <p className="mt-1 text-sm text-slate-400">Gere amostras reais com o mesmo texto, compare de ouvido e salve a voz preferida na fábrica. Nada aqui é simulado.</p></div>

      <div className={`${card} space-y-3 p-5`}>
        <h2 className="font-semibold">Provedores</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {cat.providers.map((p) => (
            <div key={p.id} className="rounded-xl border border-petrol-700 p-3 text-sm" data-testid={`prov-${p.id}`}>
              <div className="flex items-center justify-between"><span className="font-medium">{p.label}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs ${p.available ? "bg-emerald-400/15 text-emerald-300" : "bg-red-400/15 text-red-300"}`}>{p.available ? "Disponível" : "Indisponível"}</span></div>
              {!p.available && <p className="mt-1 text-red-300">{p.reason}</p>}
              <p className="mt-1 text-xs text-slate-400">{p.quality_note}</p>
              <p className="mt-1 text-xs text-slate-500">Custo: {p.cost}</p>
              <p className="text-xs text-slate-500">Limites: {p.limits}</p>
              <p className="text-xs text-slate-500">Requisitos: {p.requirements}</p>
              <p className="text-xs text-slate-500">Controles: {[p.controls.speed && "velocidade", p.controls.style && "estilo (texto)", p.controls.pitch && "tom"].filter(Boolean).join(", ") || "nenhum além da voz"} · {p.voices.length} voz(es) pt-BR</p>
            </div>
          ))}
        </div>
      </div>

      <div className={`${card} space-y-4 p-5`}>
        <h2 className="font-semibold">Gerar amostra</h2>
        <label className="block text-sm text-slate-300">Texto de teste (curto — {text.length}/{cat.max_chars})
          <textarea value={text} onChange={(e) => setText(e.target.value.slice(0, cat.max_chars))} rows={3} className={`${input} mt-1`} data-testid="vl-text" /></label>
        <div className="rounded-xl border border-petrol-700 p-3">
          <label className="block text-sm text-slate-300">Descreva a voz que você quer (opcional)
            <input value={nl} onChange={(e) => setNl(e.target.value)} className={`${input} mt-1`} data-testid="vl-nl" placeholder="Quero uma narração masculina, grave, pausada e misteriosa." /></label>
          <button className={`${ghost} mt-2`} onClick={interpret} disabled={nl.trim().length < 3 || !!busy} data-testid="vl-interpret">{busy === "nl" ? "Interpretando…" : "Interpretar pedido"}</button>
          {interp && (
            <div className="mt-3 space-y-2 text-sm" data-testid="vl-interp">
              <p className="text-slate-300">{interp.explanation}</p>
              {interp.unsupported.length > 0 && <Notice>Não é possível controlar com os provedores disponíveis: {interp.unsupported.join("; ")}.</Notice>}
            </div>
          )}
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="text-sm text-slate-300">Provedor
            <select value={provider} onChange={(e) => pick(e.target.value)} className={`${input} mt-1`} data-testid="vl-provider">
              {cat.providers.map((p) => <option key={p.id} value={p.id}>{p.label}{p.available ? "" : " — indisponível"}</option>)}</select></label>
          <label className="text-sm text-slate-300">Voz
            <select value={voice} onChange={(e) => setVoice(e.target.value)} className={`${input} mt-1`} data-testid="vl-voice">
              {cur?.voices.map((v) => <option key={v.id} value={v.id}>{v.label}{v.gender ? ` (${v.gender === "male" ? "masc." : "fem."})` : ""}</option>)}</select></label>
          {cur?.controls.speed && <label className="text-sm text-slate-300">Velocidade: {speed.toFixed(2)}×
            <input type="range" min={cur.controls.speed[0]} max={cur.controls.speed[1]} step={0.05} value={speed} onChange={(e) => setSpeed(Number(e.target.value))} className="mt-2 w-full" /></label>}
          {cur?.controls.style && <label className="text-sm text-slate-300">Estilo de entrega
            <input value={style} onChange={(e) => setStyle(e.target.value)} className={`${input} mt-1`} placeholder="ex.: voz grave, pausada e misteriosa" data-testid="vl-style" /></label>}
        </div>
        {cur && !cur.available && <Notice tone="error"><strong>{cur.label} indisponível.</strong> {cur.reason}. Requisitos: {cur.requirements}</Notice>}
        {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
        <button className={primary} onClick={generate} disabled={!cur?.available || !voice || text.trim().length < 3 || !!busy} data-testid="vl-generate">{busy === "gen" ? "Gerando…" : "Gerar amostra"}</button>
      </div>

      <div className={`${card} space-y-4 p-5`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">Amostras para comparar</h2>
          <label className="flex items-center gap-2 text-sm text-slate-300">Fábrica
            <select value={fid} onChange={(e) => setFid(e.target.value)} className="rounded-xl border border-petrol-600 bg-petrol-950/70 px-3 py-2 text-sm" data-testid="vl-factory">
              <option value="">— escolha —</option>{lines?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
        </div>
        {identity && <p className="text-xs text-slate-400" data-testid="vl-current">Voz atual de “{fname}”: {identity.provider}/{identity.voice_id}{identity.legacy ? " (padrão antigo, ainda sem identidade vocal)" : ""}.</p>}
        {ok && <Notice tone="warn">{ok}</Notice>}
        {!list?.length && <p className="text-sm text-slate-400">Nenhuma amostra ainda. Gere a primeira acima.</p>}
        <div className="space-y-3">
          {list?.map((s) => {
            const mine = identity?.provider === s.provider && identity?.voice_id === s.voice;
            return (
              <div key={s.id} className="rounded-xl border border-petrol-700 p-3" data-testid="sample">
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="font-medium">{s.provider} · {s.voice}{s.params.speed ? ` · ${s.params.speed}×` : ""}</span>
                  <span className="text-xs text-slate-500">{s.seconds}s de áudio · gerado em {(s.gen_ms / 1000).toFixed(1)}s · US$ {s.cost}</span>
                </div>
                {s.params.style && <p className="text-xs text-slate-400">Estilo: {s.params.style}</p>}
                <p className="mt-1 line-clamp-2 text-xs text-slate-500">“{s.text}”</p>
                <audio controls preload="none" src={s.audio_url} className="mt-2 w-full" />
                <div className="mt-2 flex gap-2">
                  <button className={primary} onClick={() => useSample(s)} disabled={!fid || !!busy || mine} data-testid="vl-use">{mine ? "Voz atual da fábrica" : "Usar na fábrica"}</button>
                  <button className={ghost} onClick={() => remove(s.id)}>Remover</button>
                </div>
                {!fid && <p className="mt-1 text-xs text-slate-500">Escolha uma fábrica acima para salvar esta voz.</p>}
              </div>
            );
          })}
        </div>
        <p className="text-xs text-slate-500"><Link className="text-cyan-300 hover:underline" to="/fabricas">Minhas Fábricas</Link> · a voz salva vale para os próximos vídeos; se o provedor ficar indisponível, o Piper assume e isso é registrado na produção.</p>
      </div>
    </div>
  );
}
