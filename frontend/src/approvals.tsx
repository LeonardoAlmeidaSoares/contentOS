import { ReactNode, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApprovalDetail, Publication, ReviewStatus } from "./api";
import { usePoll } from "./hooks";
import { card, ghost, input, Notice, primary } from "./studio";

const TABS: { key: ReviewStatus | "all"; label: string }[] = [
  { key: "pending", label: "Aguardando" }, { key: "approved", label: "Aprovadas" },
  { key: "changes_requested", label: "Com alterações" }, { key: "rejected", label: "Rejeitadas" },
];
const REVIEW_LABEL: Record<string, string> = { pending: "Aguardando aprovação", approved: "Aprovada", changes_requested: "Alterações solicitadas", rejected: "Rejeitada" };
const PUB_LABEL: Record<string, string> = { preparing: "Preparando envio", uploading: "Enviando…", succeeded: "Enviado como privado", failed: "Falhou", uncertain: "Resultado incerto" };

function ReviewPill({ s }: { s: string }) {
  const c = s === "approved" ? "bg-emerald-400/15 text-emerald-300" : s === "rejected" ? "bg-red-400/15 text-red-300" : s === "changes_requested" ? "bg-amber-400/15 text-amber-300" : "bg-cyan-400/15 text-cyan-300";
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${c}`}>{REVIEW_LABEL[s] ?? s}</span>;
}
const mmss = (s: number | null) => (s ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}` : "—");

export function Approvals() {
  const [tab, setTab] = useState<ReviewStatus>("pending");
  const { data, error } = usePoll(() => api.approvals(tab), [tab], 4000);
  return (
    <div className="space-y-6">
      <div><h1 className="text-2xl font-semibold">Aprovações</h1><p className="text-sm text-slate-400">Revise cada vídeo antes de qualquer publicação. Aprovar não publica automaticamente.</p></div>
      <div className="flex flex-wrap gap-2">{TABS.map((t) => (
        <button key={t.key} onClick={() => setTab(t.key as ReviewStatus)} data-testid={`tab-${t.key}`}
          className={`rounded-full px-4 py-1.5 text-sm ${tab === t.key ? "bg-cyan-400 font-semibold text-petrol-950" : "border border-petrol-600 text-slate-300 hover:border-cyan-400"}`}>{t.label}</button>))}</div>
      {error && <Notice tone="error">Não foi possível carregar as aprovações.</Notice>}
      {data && data.length === 0 && <div className={`${card} p-8 text-center text-sm text-slate-400`}>Nada por aqui{tab === "pending" ? ": nenhuma produção aguardando aprovação." : "."}</div>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data?.map((a) => (
          <Link key={a.run_id} to={`/aprovacoes/${a.run_id}`} data-testid="approval-card" className={`${card} overflow-hidden hover:border-cyan-400`}>
            {a.thumbnail_artifact_id ? <img src={api.imageUrl(a.thumbnail_artifact_id)} alt="" className="aspect-video w-full object-cover" /> : <div className="aspect-video bg-petrol-800" />}
            <div className="space-y-2 p-4"><div className="font-medium">{a.title}</div>
              <div className="text-xs text-slate-400">{a.factory_name} · {mmss(a.duration_seconds)} · {new Date(a.created_at).toLocaleDateString("pt-BR")}</div>
              <div className="flex flex-wrap gap-2"><ReviewPill s={a.review.status} />{a.publication && <span className="rounded-full bg-petrol-700 px-2.5 py-0.5 text-xs text-slate-200">{PUB_LABEL[a.publication.status]}</span>}</div></div>
          </Link>))}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block space-y-1"><span className="text-xs text-slate-400">{label}</span>{children}</label>;
}

function PublishPanel({ d, reload }: { d: ApprovalDetail; reload: () => void }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(d.defaults.title);
  const [desc, setDesc] = useState(d.defaults.description);
  const [tags, setTags] = useState(d.defaults.tags.join(", "));
  const [kids, setKids] = useState(false);
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const send = async () => {
    setBusy(true); setErr(null);
    try { await api.publish(d.run_id, { title, description: desc, tags: tags.split(",").map((t) => t.trim()).filter(Boolean), made_for_kids: kids, privacy: "private", confirm: true }); setOpen(false); reload(); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className={`${card} space-y-4 p-5`}>
      <h2 className="font-semibold">Publicação no YouTube</h2>
      {d.blockers.map((b) => <p key={b} className="text-sm text-amber-200">• {b}</p>)}
      {!open && d.can_publish && <button className={primary} onClick={() => setOpen(true)} data-testid="open-publish">Publicar como privado</button>}
      {open && (
        <div className="space-y-3" data-testid="publish-form">
          <Notice>O vídeo será enviado como <strong>PRIVADO</strong> para o canal <strong>{d.channel?.title}</strong>. Revise os dados abaixo.</Notice>
          <Field label="Título (máx. 100)"><input className={input} value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} data-testid="pub-title" /></Field>
          <Field label="Descrição"><textarea className={input} rows={6} value={desc} onChange={(e) => setDesc(e.target.value)} data-testid="pub-desc" /></Field>
          <Field label="Tags (separadas por vírgula)"><input className={input} value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
          <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={kids} onChange={(e) => setKids(e.target.checked)} />Este vídeo é feito para crianças</label>
          <label className="flex items-start gap-2 text-sm text-slate-200"><input className="mt-1" type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} data-testid="pub-confirm" />Confirmo que revisei título, descrição e vídeo e autorizo o envio privado ao YouTube.</label>
          {err && <Notice tone="error">{err}</Notice>}
          <div className="flex gap-3"><button className={primary} disabled={!ok || busy || !title.trim()} onClick={send} data-testid="pub-send">{busy ? "Enviando…" : "Enviar como privado"}</button><button className={ghost} onClick={() => setOpen(false)}>Cancelar</button></div>
        </div>)}
      {d.publications.length > 0 && <div className="space-y-3 border-t border-petrol-700 pt-4"><h3 className="text-sm font-medium text-slate-300">Histórico de envios</h3>
        {d.publications.map((p) => <PubRow key={p.id} p={p} reload={reload} />)}</div>}
    </div>
  );
}

function PubRow({ p, reload }: { p: Publication; reload: () => void }) {
  const [busy, setBusy] = useState(false);
  const tone = p.status === "succeeded" ? "text-emerald-300" : p.status === "failed" ? "text-red-300" : p.status === "uncertain" ? "text-amber-300" : "text-cyan-300";
  return (
    <div className="space-y-1 text-sm" data-testid="pub-row">
      <div className="flex flex-wrap items-center justify-between gap-2"><span className={tone} data-testid="pub-status">{PUB_LABEL[p.status] ?? p.status}</span><span className="text-xs text-slate-500">{new Date(p.created_at).toLocaleString("pt-BR")}</span></div>
      <div className="text-xs text-slate-400">“{p.title}” · {p.privacy === "private" ? "Privado" : p.privacy}{p.channel_title ? ` · ${p.channel_title}` : ""}</div>
      {p.url && <a href={p.url} target="_blank" rel="noreferrer" className="text-xs text-cyan-300 underline" data-testid="pub-url">{p.url}</a>}
      {p.error && <p className="text-xs text-slate-300">{p.error}</p>}
      {(p.status === "uncertain") && <button className={ghost} disabled={busy} onClick={async () => { setBusy(true); try { await api.resumePublication(p.id); reload(); } finally { setBusy(false); } }}>Verificar envio</button>}
    </div>
  );
}

export function ApprovalDetailPage() {
  const { id = "" } = useParams();
  const { data: d, error } = usePoll(() => api.approval(id), [id], 2500);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  if (error && !d) return <Notice tone="error">Produção não encontrada.</Notice>;
  if (!d) return <p className="text-sm text-slate-400">Carregando…</p>;
  const locked = d.publications.some((p) => ["preparing", "uploading", "succeeded", "uncertain"].includes(p.status));
  const decide = async (k: "approve" | "request_changes" | "reject") => {
    setBusy(true); setMsg(null);
    try { await api.decide(id, k, note); setNote(""); setVersion(version + 1); } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-6" key={version}>
      <div><Link to="/aprovacoes" className="text-sm text-cyan-300 hover:underline">← Aprovações</Link>
        <div className="mt-1 flex flex-wrap items-center gap-3"><h1 className="text-2xl font-semibold" data-testid="approval-title">{d.title}</h1><span data-testid="review-status"><ReviewPill s={d.review.status} /></span></div></div>
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-3">
          <div className={`${card} overflow-hidden`}>
            {d.video_artifact_id && <video controls preload="metadata" className="aspect-video w-full bg-black" src={api.imageUrl(d.video_artifact_id)} data-testid="player"
              poster={d.thumbnail_artifact_id ? api.imageUrl(d.thumbnail_artifact_id) : undefined} />}
            <div className="flex flex-wrap gap-x-6 gap-y-1 p-4 text-sm text-slate-300">
              <span>Fábrica: <Link className="text-cyan-300 hover:underline" to={`/fabricas/${d.factory_id}`}>{d.factory_name}</Link></span>
              <span>Duração: {mmss(d.duration_seconds)}</span><span>{d.scenes} cenas</span>{d.words ? <span>{d.words} palavras</span> : null}
              <Link className="text-cyan-300 hover:underline" to={`/producao/${d.run_id}`}>Ver produção</Link></div>
          </div>
          <div className={`${card} space-y-3 p-5`}>
            <h2 className="font-semibold">Decisão</h2>
            {locked ? <p className="text-sm text-slate-400">Esta produção já tem envio ao YouTube; a decisão não pode mais ser alterada.</p> : (<>
              <textarea className={input} rows={3} value={note} onChange={(e) => setNote(e.target.value)} data-testid="note" placeholder="Observações (obrigatório para solicitar alterações ou rejeitar)" />
              {msg && <Notice tone="error">{msg}</Notice>}
              <div className="flex flex-wrap gap-3">
                <button className={primary} disabled={busy} onClick={() => decide("approve")} data-testid="approve">Aprovar</button>
                <button className={ghost} disabled={busy || !note.trim()} onClick={() => decide("request_changes")} data-testid="request-changes">Solicitar alterações</button>
                <button className={`${ghost} hover:!border-red-400 hover:!text-red-300`} disabled={busy || !note.trim()} onClick={() => decide("reject")} data-testid="reject">Rejeitar</button>
              </div></>)}
            {d.review.note && <p className="text-sm text-slate-300">Última observação: “{d.review.note}”</p>}
          </div>
        </div>
        <div className="space-y-4 lg:col-span-2">
          <PublishPanel key={`${d.review.status}-${d.can_publish}-${d.publications.length}`} d={d} reload={() => setVersion(version + 1)} />
          {d.events.length > 0 && <div className={`${card} p-5`}><h2 className="mb-3 font-semibold">Histórico</h2>
            <ul className="space-y-2 text-xs text-slate-400" data-testid="events">{d.events.map((e, i) => <li key={i}><span className="text-slate-500">{new Date(e.at).toLocaleString("pt-BR")}</span> — {e.text}</li>)}</ul></div>}
        </div>
      </div>
    </div>
  );
}

export function Settings() {
  const { data: st, error } = usePoll(() => api.ytStatus(), [], 5000);
  const [cur, setCur] = useState<typeof st>(null);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const s = cur ?? st;
  const run = async (fn: () => Promise<unknown>) => { setBusy(true); setMsg(null); try { await fn(); } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); } };
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold">Configurações</h1>
      <div className={`${card} space-y-4 p-6`}>
        <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">YouTube</h2>
          {s && <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${s.status === "connected" ? "bg-emerald-400/15 text-emerald-300" : s.status === "revoked" ? "bg-red-400/15 text-red-300" : "bg-petrol-700 text-slate-300"}`} data-testid="yt-status">
            {{ connected: "Conectado", revoked: "Acesso revogado", pending: "Não conectado", unconfigured: "Não configurado" }[s.status]}</span>}</div>
        {error && <Notice tone="error">Não foi possível consultar o status.</Notice>}
        {s && !s.configured && <Notice><strong>Credenciais do Google ainda não configuradas.</strong> {s.help}</Notice>}
        {s?.status === "revoked" && <Notice tone="error">{s.message ?? "A autorização foi revogada."} Conecte o canal novamente.</Notice>}
        {s?.channel && (<div className="space-y-3"><p className="text-sm text-slate-300">Canal conectado: <strong className="text-cyan-300" data-testid="yt-channel">{s.channel.title}</strong></p>
          <p className="text-xs text-slate-500">Permissões: enviar vídeos e ler informações do canal. O ContentOS nunca vê sua senha do Google. Somente envios privados nesta versão.</p>
          <div className="flex gap-3"><button className={ghost} disabled={busy} onClick={() => run(async () => setCur(await api.ytCheck()))}>Verificar conexão</button>
            <button className={ghost} disabled={busy} onClick={() => run(async () => { setCur(await api.ytDisconnect()); setAuthUrl(null); })} data-testid="yt-disconnect">Desconectar canal</button></div></div>)}
        {s?.configured && s.status !== "connected" && (
          <div className="space-y-4">
            {!authUrl ? <button className={primary} disabled={busy} data-testid="yt-connect" onClick={() => run(async () => setAuthUrl((await api.ytConnect()).auth_url))}>Conectar canal do YouTube</button> : (
              <ol className="list-decimal space-y-3 pl-5 text-sm text-slate-300">
                <li>Abra a página de autorização do Google: <a href={authUrl} target="_blank" rel="noreferrer" className="text-cyan-300 underline" data-testid="yt-auth-link">autorizar no Google</a> e escolha o canal.</li>
                <li>Ao final, o navegador mostrará uma página de erro (“não é possível acessar o site”). <strong>É esperado.</strong> Copie o endereço completo da barra de endereços (começa com <code className="rounded bg-black/30 px-1">{s.redirect_uri}</code>).</li>
                <li>Cole aqui:<textarea className={`${input} mt-2`} rows={2} value={pasted} onChange={(e) => setPasted(e.target.value)} data-testid="yt-paste" placeholder={`${s.redirect_uri}?state=…&code=…`} />
                  <button className={`${primary} mt-2`} disabled={busy || pasted.trim().length < 10} data-testid="yt-finish" onClick={() => run(async () => { setCur(await api.ytCallback(pasted.trim())); setAuthUrl(null); setPasted(""); })}>Concluir conexão</button></li>
              </ol>)}
          </div>)}
        {msg && <Notice tone="error">{msg}</Notice>}
      </div>
    </div>
  );
}
