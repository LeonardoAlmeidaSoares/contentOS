import { ReactNode, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApprovalDetail, Publication, ReviewStatus } from "./api";
import { usePoll } from "./hooks";
import { card, ghost, input, Notice, primary } from "./studio";
import { FactoryFilter } from "./components/CollectionControls";
import { ProductionAssets } from "./components/ProductionAssets";
import { Badge, money } from "./ui";
import {
  EmptyState,
  FactoryCover,
  Icon,
  LoadingCards,
  PageHeading,
} from "./components/StudioVisuals";

const TABS: { key: ReviewStatus | "all"; label: string }[] = [
  { key: "pending", label: "Aguardando" },
  { key: "approved", label: "Aprovadas" },
  { key: "changes_requested", label: "Com alterações" },
  { key: "rejected", label: "Rejeitadas" },
];
const REVIEW_LABEL: Record<string, string> = {
  pending: "Aguardando aprovação",
  approved: "Aprovada",
  changes_requested: "Alterações solicitadas",
  rejected: "Rejeitada",
};
const PUB_LABEL: Record<string, string> = {
  preparing: "Preparando envio",
  uploading: "Enviando…",
  succeeded: "Enviado como privado",
  failed: "Falhou",
  uncertain: "Resultado incerto",
};

function ReviewPill({ s }: { s: string }) {
  const c =
    s === "approved"
      ? "bg-emerald-400/15 text-emerald-300"
      : s === "rejected"
        ? "bg-red-400/15 text-red-300"
        : s === "changes_requested"
          ? "bg-amber-400/15 text-amber-300"
          : "bg-cyan-400/15 text-cyan-300";
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${c}`}>
      {REVIEW_LABEL[s] ?? s}
    </span>
  );
}
const mmss = (s: number | null) =>
  s
    ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`
    : "—";

export function Approvals() {
  const [tab, setTab] = useState<ReviewStatus>("pending");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [factory, setFactory] = useState("all");
  const { data: all, error } = usePoll(() => api.approvals("all"), [], 4000);
  const filtered = all?.filter(
    (a) => factory === "all" || a.factory_id === factory,
  );
  const data = filtered?.filter((a) => a.review.status === tab);
  const options = Array.from(
    new Map(
      (all ?? [])
        .filter((a) => a.factory_id)
        .map((a) => [
          a.factory_id!,
          { id: a.factory_id!, name: a.factory_name ?? "Fábrica" },
        ]),
    ).values(),
  );
  const selectedRunId = selectedId ?? data?.[0]?.run_id;
  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Seu olhar faz a diferença"
        title="Aprovações"
        description="Dê o último olhar em cada criação. Revise o vídeo, compartilhe ajustes e decida quando ele está pronto."
      />
      <div className="flex items-center gap-3 rounded-xl border border-cyan-300/10 bg-cyan-300/5 px-5 py-4 text-sm text-slate-300">
        <Icon name="check" size={19} className="text-cyan-300" />
        Aprovar não publica automaticamente. O envio ao YouTube é uma etapa
        separada.
      </div>
      <div className="filter-bar">
        <div className="filter-tabs w-fit">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => {
                setTab(t.key as ReviewStatus);
                setSelectedId(null);
              }}
              data-testid={`tab-${t.key}`}
              aria-pressed={tab === t.key}
            >
              {t.label}
              <span className="tab-count">
                {filtered
                  ? filtered.filter((a) => a.review.status === t.key).length
                  : "—"}
              </span>
            </button>
          ))}
        </div>
        <FactoryFilter
          value={factory}
          options={options}
          onChange={(v) => {
            setFactory(v);
            setSelectedId(null);
          }}
          label="Filtrar aprovações por fábrica"
        />
      </div>
      {error && (
        <Notice tone="error">Não foi possível carregar as aprovações.</Notice>
      )}
      {!data && !error && <LoadingCards />}
      {data && data.length === 0 && !selectedId && (
        <EmptyState
          icon="check"
          title={
            tab === "pending"
              ? "Tudo revisado por aqui"
              : "Nenhuma produção nesta etapa"
          }
        >
          {tab === "pending"
            ? "Quando um vídeo ficar pronto, ele chega aqui para receber o seu olhar."
            : "Selecione outra etapa para encontrar suas produções."}
        </EmptyState>
      )}
      <div className="approval-review-layout">
        <div className="space-y-3">
          {data?.length === 0 && selectedId && (
            <p className="studio-card p-4 text-sm text-slate-400">
              Nenhum outro conteúdo neste filtro. A revisão selecionada continua
              aberta.
            </p>
          )}
          {data?.map((a) => (
            <button
              type="button"
              key={a.run_id}
              onClick={() => {
                setSelectedId(a.run_id);
                if (window.matchMedia("(max-width:1279px)").matches)
                  document
                    .getElementById("approval-preview")
                    ?.scrollIntoView({ behavior: "smooth" });
              }}
              aria-pressed={selectedRunId === a.run_id}
              data-testid="approval-card"
              className="approval-choice"
            >
              <FactoryCover
                factory={{
                  name: a.factory_name ?? a.title,
                  description: "",
                  config: {},
                }}
                image={
                  a.thumbnail_artifact_id
                    ? api.imageUrl(a.thumbnail_artifact_id)
                    : undefined
                }
              />
              <div className="space-y-2 p-4">
                <div className="font-medium">{a.title}</div>
                <div className="text-xs text-slate-400">
                  {a.factory_name} · {mmss(a.duration_seconds)} ·{" "}
                  {new Date(a.created_at).toLocaleDateString("pt-BR")}
                </div>
                <div className="flex flex-wrap gap-2">
                  <ReviewPill s={a.review.status} />
                  {a.publication && (
                    <span className="rounded-full bg-petrol-700 px-2.5 py-0.5 text-xs text-slate-200">
                      {PUB_LABEL[a.publication.status]}
                    </span>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
        {selectedRunId && (
          <div id="approval-preview" className="min-w-0">
            <ApprovalDetailPage
              key={selectedRunId}
              runId={selectedRunId}
              embedded
            />
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs text-slate-400">{label}</span>
      {children}
    </label>
  );
}

function PublishPanel({
  d,
  reload,
}: {
  d: ApprovalDetail;
  reload: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(d.defaults.title);
  const [desc, setDesc] = useState(d.defaults.description);
  const [tags, setTags] = useState(d.defaults.tags.join(", "));
  const [kids, setKids] = useState(false);
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const send = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.publish(d.run_id, {
        title,
        description: desc,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        made_for_kids: kids,
        privacy: "private",
        confirm: true,
      });
      setOpen(false);
      reload();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={`${card} space-y-4 p-5`}>
      <h2 className="font-semibold">Publicação no YouTube</h2>
      {d.blockers.map((b) => (
        <p key={b} className="text-sm text-amber-200">
          • {b}
        </p>
      ))}
      {!open && d.can_publish && (
        <button
          className={primary}
          onClick={() => setOpen(true)}
          data-testid="open-publish"
        >
          Publicar como privado
        </button>
      )}
      {open && (
        <div className="space-y-3" data-testid="publish-form">
          <Notice>
            O vídeo será enviado como <strong>PRIVADO</strong> para o canal{" "}
            <strong>{d.channel?.title}</strong>. Revise os dados abaixo.
          </Notice>
          <Field label="Título (máx. 100)">
            <input
              className={input}
              value={title}
              maxLength={100}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="pub-title"
            />
          </Field>
          <Field label="Descrição">
            <textarea
              className={input}
              rows={6}
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              data-testid="pub-desc"
            />
          </Field>
          <Field label="Tags (separadas por vírgula)">
            <input
              className={input}
              value={tags}
              onChange={(e) => setTags(e.target.value)}
            />
          </Field>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={kids}
              onChange={(e) => setKids(e.target.checked)}
            />
            Este vídeo é feito para crianças
          </label>
          <label className="flex items-start gap-2 text-sm text-slate-200">
            <input
              className="mt-1"
              type="checkbox"
              checked={ok}
              onChange={(e) => setOk(e.target.checked)}
              data-testid="pub-confirm"
            />
            Confirmo que revisei título, descrição e vídeo e autorizo o envio
            privado ao YouTube.
          </label>
          {err && <Notice tone="error">{err}</Notice>}
          <div className="flex gap-3">
            <button
              className={primary}
              disabled={!ok || busy || !title.trim()}
              onClick={send}
              data-testid="pub-send"
            >
              {busy ? "Enviando…" : "Enviar como privado"}
            </button>
            <button className={ghost} onClick={() => setOpen(false)}>
              Cancelar
            </button>
          </div>
        </div>
      )}
      {d.publications.length > 0 && (
        <div className="space-y-3 border-t border-petrol-700 pt-4">
          <h3 className="text-sm font-medium text-slate-300">
            Histórico de envios
          </h3>
          {d.publications.map((p) => (
            <PubRow key={p.id} p={p} reload={reload} />
          ))}
        </div>
      )}
    </div>
  );
}

function PubRow({ p, reload }: { p: Publication; reload: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tone =
    p.status === "succeeded"
      ? "text-emerald-300"
      : p.status === "failed"
        ? "text-red-300"
        : p.status === "uncertain"
          ? "text-amber-300"
          : "text-cyan-300";
  return (
    <div className="space-y-1 text-sm" data-testid="pub-row">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={tone} data-testid="pub-status">
          {PUB_LABEL[p.status] ?? p.status}
        </span>
        <span className="text-xs text-slate-500">
          {new Date(p.created_at).toLocaleString("pt-BR")}
        </span>
      </div>
      <div className="text-xs text-slate-400">
        “{p.title}” · {p.privacy === "private" ? "Privado" : p.privacy}
        {p.channel_title ? ` · ${p.channel_title}` : ""}
      </div>
      {p.url && (
        <a
          href={p.url}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-cyan-300 underline"
          data-testid="pub-url"
        >
          {p.url}
        </a>
      )}
      {p.error && <p className="text-xs text-slate-300">{p.error}</p>}
      {error && <Notice tone="error">{error}</Notice>}
      {p.status === "uncertain" && (
        <button
          className={ghost}
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await api.resumePublication(p.id);
              reload();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Verificar envio
        </button>
      )}
    </div>
  );
}

export function ApprovalDetailPage({
  runId,
  embedded = false,
}: { runId?: string; embedded?: boolean } = {}) {
  const { id: paramId = "" } = useParams();
  const id = runId ?? paramId;
  const Title = embedded ? "h2" : "h1";
  const { data: assets, error: assetsError } = usePoll(
    () => api.run(id),
    [id],
    10000,
    () => false,
  );
  const [version, setVersion] = useState(0);
  const { data: d, error } = usePoll(
    () => api.approval(id),
    [id, version],
    2500,
  );
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  if (error && !d)
    return <Notice tone="error">Produção não encontrada.</Notice>;
  if (!d) return <p className="text-sm text-slate-400">Carregando…</p>;
  const locked = d.publications.some((p) =>
    ["preparing", "uploading", "succeeded", "uncertain"].includes(p.status),
  );
  const decide = async (k: "approve" | "request_changes" | "reject") => {
    setBusy(true);
    setMsg(null);
    try {
      await api.decide(id, k, note);
      setNote("");
      setVersion(version + 1);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/aprovacoes"
          className={`text-sm text-cyan-300 hover:underline ${embedded ? "hidden" : ""}`}
        >
          ← Aprovações
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <Title
            className="text-2xl font-semibold"
            data-testid="approval-title"
          >
            {d.title}
          </Title>
          <span data-testid="review-status">
            <ReviewPill s={d.review.status} />
          </span>
        </div>
      </div>
      {error && (
        <Notice tone="error">Não foi possível atualizar a revisão.</Notice>
      )}
      <div
        className={
          embedded
            ? "space-y-5"
            : "grid gap-6 xl:grid-cols-[minmax(0,2.4fr)_minmax(280px,1fr)]"
        }
      >
        <div className="space-y-4">
          <div className={embedded ? "review-preview-grid" : ""}>
            <div className={`${card} overflow-hidden`}>
              {d.video_artifact_id && (
                <video
                  controls
                  preload="metadata"
                  className="aspect-video w-full bg-black"
                  src={api.imageUrl(d.video_artifact_id)}
                  data-testid="player"
                  poster={
                    d.thumbnail_artifact_id
                      ? api.imageUrl(d.thumbnail_artifact_id)
                      : undefined
                  }
                />
              )}
              <div className="flex flex-wrap gap-x-6 gap-y-1 p-4 text-sm text-slate-300">
                <span>
                  Fábrica:{" "}
                  <Link
                    className="text-cyan-300 hover:underline"
                    to={`/fabricas/${d.factory_id}`}
                  >
                    {d.factory_name}
                  </Link>
                </span>
                <span>Duração: {mmss(d.duration_seconds)}</span>
                <span>{d.scenes} cenas</span>
                {d.words ? <span>{d.words} palavras</span> : null}
                <Link
                  className="text-cyan-300 hover:underline"
                  to={`/producao/${d.run_id}`}
                >
                  Ver produção
                </Link>
              </div>
            </div>
            {embedded && (
              <aside className="studio-card review-summary p-4">
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                  <Icon name="file" size={17} className="text-cyan-300" />
                  Resumo do conteúdo
                </h3>
                <p className="line-clamp-3 whitespace-pre-wrap text-xs leading-relaxed text-slate-300">
                  {d.defaults.description}
                </p>
                <dl className="summary-list mt-4">
                  <div>
                    <dt>Duração</dt>
                    <dd>{mmss(d.duration_seconds)}</dd>
                  </div>
                  <div>
                    <dt>Cenas</dt>
                    <dd>{d.scenes}</dd>
                  </div>
                  {d.words !== null && (
                    <div>
                      <dt>Palavras</dt>
                      <dd>{d.words}</dd>
                    </div>
                  )}
                  <div>
                    <dt>Créditos de imagens</dt>
                    <dd>{d.has_credits ? "Disponíveis" : "Não informados"}</dd>
                  </div>
                </dl>
                <p className="mt-4 text-xs leading-relaxed text-slate-400">
                  A decisão é humana. Aprovar libera a preparação do envio, que
                  exige outra confirmação.
                </p>
                <Link to={`/aprovacoes/${id}`} className="text-link mt-4">
                  Abrir revisão completa <Icon name="arrow" size={14} />
                </Link>
              </aside>
            )}
          </div>
          <div className={`${card} space-y-3 p-5`}>
            <h2 className="font-semibold">Seu parecer</h2>
            <p className="text-xs text-slate-400">
              Aprovar libera a preparação do envio. Você confirma a publicação
              separadamente.
            </p>
            {locked ? (
              <p className="text-sm text-slate-400">
                Esta produção já tem envio ao YouTube; a decisão não pode mais
                ser alterada.
              </p>
            ) : (
              <>
                <textarea
                  className={input}
                  rows={3}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  aria-label="Observações da revisão"
                  data-testid="note"
                  placeholder="Observações (obrigatório para solicitar alterações ou rejeitar)"
                />
                {msg && <Notice tone="error">{msg}</Notice>}
                <div className="flex flex-wrap gap-3">
                  <button
                    className={primary}
                    disabled={busy}
                    onClick={() => decide("approve")}
                    data-testid="approve"
                  >
                    Aprovar
                  </button>
                  <button
                    className={ghost}
                    disabled={busy || !note.trim()}
                    onClick={() => decide("request_changes")}
                    data-testid="request-changes"
                  >
                    Solicitar alterações
                  </button>
                  <button
                    className={`${ghost} hover:!border-red-400 hover:!text-red-300`}
                    disabled={busy || !note.trim()}
                    onClick={() => decide("reject")}
                    data-testid="reject"
                  >
                    Rejeitar
                  </button>
                </div>
              </>
            )}
            {d.review.note && (
              <p className="text-sm text-slate-300">
                Última observação: “{d.review.note}”
              </p>
            )}
          </div>
          <details className={`${card} p-5`}>
            <summary className="cursor-pointer text-sm font-semibold">
              Descrição do vídeo
            </summary>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-slate-400">
              {d.defaults.description}
            </p>
          </details>
        </div>
        <div className="space-y-4">
          <PublishPanel
            key={`${d.review.status}-${d.can_publish}-${d.publications.length}`}
            d={d}
            reload={() => setVersion(version + 1)}
          />
          {d.events.length > 0 && (
            <div className={`${card} p-5`}>
              <h2 className="mb-3 font-semibold">Histórico</h2>
              <ul
                className="space-y-2 text-xs text-slate-400"
                data-testid="events"
              >
                {d.events.map((e, i) => (
                  <li key={i}>
                    <span className="text-slate-500">
                      {new Date(e.at).toLocaleString("pt-BR")}
                    </span>{" "}
                    — {e.text}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
      {assetsError && (
        <Notice tone="error">
          Não foi possível carregar os materiais desta produção.
        </Notice>
      )}
      {assets && <ProductionAssets run={assets} />}
    </div>
  );
}

export function Settings() {
  const { data: studio, error: studioError } = usePoll(
    () => api.studioStatus(),
    [],
    15000,
  );
  const [section, setSection] = useState("integrations");
  const { data: providers, error: providerError } = usePoll(
    async () => (section === "providers" ? api.providers() : null),
    [section],
    10000,
    (d) => !!d,
  );
  const { data: ready, error: readyError } = usePoll(
    async () => (section === "advanced" ? api.ready() : null),
    [section],
    15000,
    (d) => !!d,
  );
  const [motion, setMotion] = useState(
    document.documentElement.dataset.motion === "reduced"
      ? "reduced"
      : "system",
  );
  const [preferenceError, setPreferenceError] = useState<string | null>(null);
  const changeMotion = (value: string) => {
    setMotion(value);
    document.documentElement.dataset.motion = value;
    setPreferenceError(null);
    try {
      localStorage.setItem("contentos-motion", value);
    } catch {
      setPreferenceError(
        "A preferência foi aplicada, mas não pôde ser salva neste navegador.",
      );
    }
  };
  const { data: st, error } = usePoll(() => api.ytStatus(), [], 5000);
  const [cur, setCur] = useState<typeof st>(null);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const s = cur ?? st;
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-7">
      <PageHeading
        eyebrow="Seu estúdio, do seu jeito"
        title="Configurações"
        description="Cuide das conexões e dos recursos que dão vida às suas produções."
      />
      <div className="filter-tabs w-fit">
        {[
          ["integrations", "Integrações"],
          ["providers", "Provedores"],
          ["preferences", "Preferências"],
          ["advanced", "Avançado"],
        ].map(([k, v]) => (
          <button
            key={k}
            aria-pressed={section === k}
            onClick={() => setSection(k)}
          >
            {v}
          </button>
        ))}
      </div>
      {section === "integrations" && (
        <div className="settings-integrations">
          <div className={`${card} space-y-4 p-6`}>
            <div className="flex items-center justify-between gap-3">
              <h2 className="flex items-center gap-3 text-lg font-semibold">
                <Icon name="spark" className="text-cyan-300" />
                Assistente criativo
              </h2>
              <span
                className={`rounded-full px-3 py-1 text-xs ${studio?.gemini.configured ? "bg-emerald-300/10 text-emerald-200" : "bg-amber-300/10 text-amber-200"}`}
              >
                {studio
                  ? studio.gemini.configured
                    ? "Configurado"
                    : "Não configurado"
                  : "Consultando…"}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-slate-400">
              O Gemini ajuda a transformar sua ideia em uma fábrica e a escrever
              roteiros com a identidade do seu projeto.
            </p>
            {studioError && (
              <Notice tone="error">
                Não foi possível consultar o assistente.
              </Notice>
            )}
            {studio && !studio.gemini.configured && (
              <details className="text-sm">
                <summary className="cursor-pointer text-cyan-200">
                  Como conectar o assistente
                </summary>
                <p className="mt-3 leading-relaxed text-slate-400">
                  Adicione a chave <code>GEMINI_API_KEY</code> ao arquivo de
                  ambiente do servidor e reinicie somente a instância
                  correspondente.{" "}
                  <a
                    href="https://aistudio.google.com/apikey"
                    className="text-cyan-200 underline"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Obter chave no Google AI Studio
                  </a>
                  .
                </p>
              </details>
            )}
          </div>
          <div className={`${card} space-y-4 p-6`}>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">YouTube</h2>
              {s && (
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${s.status === "connected" ? "bg-emerald-400/15 text-emerald-300" : s.status === "revoked" ? "bg-red-400/15 text-red-300" : "bg-petrol-700 text-slate-300"}`}
                  data-testid="yt-status"
                >
                  {
                    {
                      connected: "Conectado",
                      revoked: "Acesso revogado",
                      pending: "Não conectado",
                      unconfigured: "Não configurado",
                    }[s.status]
                  }
                </span>
              )}
            </div>
            {error && (
              <Notice tone="error">Não foi possível consultar o status.</Notice>
            )}
            <p className="text-sm leading-relaxed text-slate-400">
              Conecte seu canal para enviar vídeos aprovados. Você sempre
              confirma cada envio, que será privado.
            </p>
            {!s && !error && (
              <p role="status" className="text-sm text-slate-500">
                Consultando conexão…
              </p>
            )}
            {s && !s.configured && (
              <Notice>
                <strong>Credenciais do Google ainda não configuradas.</strong>
                <details className="mt-2">
                  <summary className="cursor-pointer">
                    Instruções para configurar
                  </summary>
                  <p className="mt-2">{s.help}</p>
                </details>
              </Notice>
            )}
            {s?.status === "revoked" && (
              <Notice tone="error">
                {s.message ?? "A autorização foi revogada."} Conecte o canal
                novamente.
              </Notice>
            )}
            {s?.channel && (
              <div className="space-y-3">
                <p className="text-sm text-slate-300">
                  Canal conectado:{" "}
                  <strong className="text-cyan-300" data-testid="yt-channel">
                    {s.channel.title}
                  </strong>
                </p>
                <p className="text-xs text-slate-500">
                  Permissões: enviar vídeos e ler informações do canal. O
                  ContentOS nunca vê sua senha do Google. Somente envios
                  privados nesta versão.
                </p>
                <div className="flex gap-3">
                  <button
                    className={ghost}
                    disabled={busy}
                    onClick={() => run(async () => setCur(await api.ytCheck()))}
                  >
                    Verificar conexão
                  </button>
                  <button
                    className={ghost}
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        setCur(await api.ytDisconnect());
                        setAuthUrl(null);
                      })
                    }
                    data-testid="yt-disconnect"
                  >
                    Desconectar canal
                  </button>
                </div>
              </div>
            )}
            {s?.configured && s.status !== "connected" && (
              <div className="space-y-4">
                {!authUrl ? (
                  <button
                    className={primary}
                    disabled={busy}
                    data-testid="yt-connect"
                    onClick={() =>
                      run(async () =>
                        setAuthUrl((await api.ytConnect()).auth_url),
                      )
                    }
                  >
                    Conectar canal do YouTube
                  </button>
                ) : (
                  <ol className="list-decimal space-y-3 pl-5 text-sm text-slate-300">
                    <li>
                      Abra a página de autorização do Google:{" "}
                      <a
                        href={authUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="text-cyan-300 underline"
                        data-testid="yt-auth-link"
                      >
                        autorizar no Google
                      </a>{" "}
                      e escolha o canal.
                    </li>
                    <li>
                      Ao final, o navegador mostrará uma página de erro (“não é
                      possível acessar o site”). <strong>É esperado.</strong>{" "}
                      Copie o endereço completo da barra de endereços (começa
                      com{" "}
                      <code className="rounded bg-black/30 px-1">
                        {s.redirect_uri}
                      </code>
                      ).
                    </li>
                    <li>
                      Cole aqui:
                      <textarea
                        className={`${input} mt-2`}
                        rows={2}
                        value={pasted}
                        onChange={(e) => setPasted(e.target.value)}
                        data-testid="yt-paste"
                        placeholder={`${s.redirect_uri}?state=…&code=…`}
                      />
                      <button
                        className={`${primary} mt-2`}
                        disabled={busy || pasted.trim().length < 10}
                        data-testid="yt-finish"
                        onClick={() =>
                          run(async () => {
                            setCur(await api.ytCallback(pasted.trim()));
                            setAuthUrl(null);
                            setPasted("");
                          })
                        }
                      >
                        Concluir conexão
                      </button>
                    </li>
                  </ol>
                )}
              </div>
            )}
            {msg && <Notice tone="error">{msg}</Notice>}
          </div>
        </div>
      )}
      {section === "providers" && (
        <section className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">Provedores de criação</h2>
              <p className="mt-2 text-sm text-slate-400">
                Conexões, modelos disponíveis e limites de uso do estúdio.
              </p>
            </div>
            <Link to="/provedores/novo" className={primary}>
              <Icon name="plus" size={16} />
              Cadastrar provedor
            </Link>
          </div>
          {providerError && (
            <Notice tone="error">
              Não foi possível consultar os provedores.
            </Notice>
          )}
          {!providers && !providerError && <LoadingCards />}
          {providers?.length === 0 && (
            <EmptyState icon="settings" title="Nenhum provedor configurado">
              Adicione uma conexão para disponibilizar modelos ao estúdio.
            </EmptyState>
          )}
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {providers?.map((p) => (
              <article
                key={p.id}
                className="studio-card flex min-w-0 flex-col gap-4 p-5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="rounded-xl bg-cyan-300/10 p-2 text-cyan-300">
                    <Icon name="spark" />
                  </span>
                  <Badge status={p.active ? "active" : "inactive"} />
                </div>
                <div>
                  <h3 className="text-lg font-semibold">{p.name}</h3>
                  <p className="mt-1 text-xs text-slate-400">
                    {p.service_label}
                  </p>
                </div>
                <p className="text-xs leading-relaxed text-slate-400">
                  {p.models.filter((m) => m.active !== false).length} modelos
                  disponíveis ·{" "}
                  {p.has_credentials
                    ? "Credencial cadastrada"
                    : "Sem credencial cadastrada"}
                </p>
                <dl className="summary-list">
                  <div>
                    <dt>Uso no mês</dt>
                    <dd>{money(p.month_cost)}</dd>
                  </div>
                  <div>
                    <dt>Limite mensal</dt>
                    <dd>
                      {p.limit_month_usd === null
                        ? "Sem limite"
                        : money(p.limit_month_usd)}
                    </dd>
                  </div>
                </dl>
                <Link
                  to={`/provedores/${p.id}`}
                  className="studio-ghost mt-auto text-xs"
                >
                  Gerenciar provedor <Icon name="arrow" size={14} />
                </Link>
              </article>
            ))}
          </div>
        </section>
      )}
      {section === "preferences" && (
        <div className={`${card} max-w-4xl space-y-4 p-6`}>
          <h2 className="text-lg font-semibold">Uma experiência confortável</h2>
          <p className="text-sm text-slate-400">
            Estas preferências ficam salvas neste navegador.
          </p>
          {preferenceError && <Notice tone="error">{preferenceError}</Notice>}
          <dl className="divide-y divide-white/5 text-sm">
            <div className="flex justify-between gap-4 py-4">
              <dt className="text-slate-400">Aparência</dt>
              <dd>Estúdio escuro</dd>
            </div>
            <div className="flex justify-between gap-4 py-4">
              <dt className="text-slate-400">Idioma</dt>
              <dd>Português do Brasil</dd>
            </div>
            <div className="flex justify-between gap-4 py-4">
              <dt className="text-slate-400">Animações</dt>
              <dd>
                <select
                  className={input}
                  aria-label="Preferência de animações"
                  value={motion}
                  onChange={(e) => changeMotion(e.target.value)}
                >
                  <option value="system">Seguir o dispositivo</option>
                  <option value="reduced">Reduzir movimentos</option>
                </select>
              </dd>
            </div>
          </dl>
        </div>
      )}
      {section === "advanced" && (
        <div className="space-y-5">
          <section className="studio-card p-5">
            <h2 className="mb-4 text-lg font-semibold">
              Disponibilidade do estúdio
            </h2>
            {readyError && (
              <Notice tone="error">
                Não foi possível verificar os serviços.
              </Notice>
            )}
            {!ready && !readyError && (
              <p className="text-sm text-slate-400" role="status">
                Consultando serviços…
              </p>
            )}
            <div className="grid gap-4 sm:grid-cols-3">
              {ready &&
                Object.entries(ready.checks).map(([key, value]) => (
                  <div
                    className="rounded-xl border border-white/10 p-4"
                    key={key}
                  >
                    <p className="text-sm font-medium">
                      {{
                        postgres: "Banco de dados",
                        redis: "Fila de produção",
                        minio: "Arquivos",
                      }[key] ?? key}
                    </p>
                    <p
                      className={`mt-2 text-xs ${value === "ok" ? "text-emerald-200" : "text-amber-200"}`}
                    >
                      {value === "ok" ? "Disponível" : "Indisponível"}
                    </p>
                  </div>
                ))}
            </div>
          </section>
          <div className={`${card} space-y-4 p-6`}>
            <h2 className="text-lg font-semibold">Recursos de produção</h2>
            {studio ? (
              <dl className="space-y-3 text-sm text-slate-400">
                <div className="flex justify-between gap-3">
                  <dt>Montagem de vídeo</dt>
                  <dd>{studio.ffmpeg ? "Disponível" : "Indisponível"}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt>Vozes locais</dt>
                  <dd>
                    {studio.voice.engines.join(", ") || "Nenhuma disponível"}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt>Modelo do assistente</dt>
                  <dd className="break-all text-right">
                    {studio.gemini.model}
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="text-sm text-slate-400">
                {studioError ? "Falha ao consultar recursos." : "Carregando…"}
              </p>
            )}
          </div>
          <div className={`${card} space-y-3 p-6`}>
            <h2 className="mb-4 text-lg font-semibold">
              Ferramentas avançadas
            </h2>
            {[
              ["/visao-geral", "Saúde da infraestrutura"],
              ["/linhas", "Linhas de produção"],
              ["/execucoes", "Execuções e registros"],
              ["/provedores", "Provedores e limites"],
            ].map(([to, label]) => (
              <Link
                className="flex items-center justify-between rounded-lg border border-white/10 p-4 text-sm text-slate-300 hover:border-cyan-300/40"
                key={to}
                to={to}
              >
                {label}
                <Icon name="arrow" size={16} />
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
