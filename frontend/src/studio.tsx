import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useLocation } from "react-router-dom";
import {
  api,
  ApprovalItem,
  Artifact,
  ChatMsg,
  ChatReply,
  Line,
  PreviewRow,
  Run,
  RunSummary,
  StudioStatus,
} from "./api";
import { usePoll } from "./hooks";
import { isActiveRun, money } from "./ui";
import {
  EmptyState,
  FactoryCover,
  Icon,
  LoadingCards,
  PageHeading,
  dateLabel,
} from "./components/StudioVisuals";
import { ProductionCard } from "./pages/StudioCollections";
import { ProductionWorkspace } from "./components/ProductionMaterials";
import { ProductionAssets } from "./components/ProductionAssets";

// ---------- componentes visuais ----------
export const card = "studio-card";
export const primary = "studio-primary";
export const ghost = "studio-ghost";
export const input = "studio-input";

const STEP_LABELS: Record<string, string> = {
  script: "Escrevendo o roteiro",
  scenes: "Dividindo em cenas",
  images: "Buscando imagens",
  narration: "Gravando a narração",
  subtitles: "Sincronizando legendas",
  render: "Montando o vídeo",
  export: "Validando e exportando",
};
const RUN_LABEL: Record<string, string> = {
  queued: "Na fila",
  running: "Produzindo",
  retrying: "Tentando de novo",
  succeeded: "Pronto",
  failed: "Falhou",
  cancelled: "Cancelada",
};

export function Pill({ status }: { status: string }) {
  const c =
    status === "succeeded"
      ? "bg-emerald-400/15 text-emerald-300"
      : status === "failed"
        ? "bg-red-400/15 text-red-300"
        : status === "cancelled"
          ? "bg-slate-400/15 text-slate-300"
          : "bg-cyan-400/15 text-cyan-300";
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${c}`}>
      {RUN_LABEL[status] ?? status}
    </span>
  );
}

export function Notice({
  tone = "warn",
  children,
}: {
  tone?: "warn" | "error";
  children: ReactNode;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-xl border px-4 py-3 text-sm ${tone === "error" ? "border-red-400/40 bg-red-400/10 text-red-200" : "border-amber-400/40 bg-amber-400/10 text-amber-200"}`}
    >
      {children}
    </div>
  );
}

function useThumbs(): Record<string, string> {
  const { data } = usePoll(() => api.artifacts(), [], 4000);
  const m: Record<string, string> = {};
  (data ?? []).forEach((a: Artifact) => {
    if (a.filename === "miniatura.jpg") m[a.run_id] = a.id;
  });
  return m;
}
const useFactories = () =>
  usePoll(
    async () =>
      (await api.lines()).filter((l) => l.pipeline === "video_youtube"),
    [],
    3000,
  );
const cfgNum = (l: Line, k: string) => Number(l.config[k] ?? 0);
const freqText = (f: number) =>
  f ? `${f} vídeo(s) por semana` : "Sob demanda";

function SetupNotice({ st }: { st: StudioStatus | null }) {
  if (!st || (st.gemini.configured && st.ffmpeg && st.voice.engines.length))
    return null;
  return (
    <div className="rounded-xl border border-amber-300/15 bg-amber-300/5 px-4 py-3 text-xs leading-relaxed text-amber-100/80">
      {!st.gemini.configured && (
        <p>
          <strong>Gemini não configurado.</strong> A criação com IA precisa de
          uma conexão.{" "}
          <Link to="/configuracoes" className="underline underline-offset-4">
            Configurar assistente
          </Link>
          . Você ainda pode produzir com seu próprio roteiro.
        </p>
      )}
      {!st.ffmpeg && (
        <p>
          Montagem de vídeo indisponível no servidor. Verifique as configurações
          avançadas.
        </p>
      )}
      {st.voice.engines.length === 0 && (
        <p>
          Nenhuma voz local disponível. Verifique as configurações avançadas.
        </p>
      )}
    </div>
  );
}

export function Home() {
  const nav = useNavigate();
  const [text, setText] = useState("");
  const { data: fs, error: factoryError } = useFactories();
  const { data: runs, error: runError } = usePoll(() => api.runs(), [], 4000);
  const { data: reviews, error: reviewError } = usePoll(
    () => api.approvals("all"),
    [],
    5000,
  );
  const thumbs = useThumbs();
  const videoRuns = runs?.filter((r) => r.pipeline === "video_youtube");
  const active = fs?.flatMap((f) => (f.active_run ? [f.active_run] : []));
  const pending = reviews?.filter((r) => r.review.status === "pending");
  const recent = videoRuns?.filter((r) => !isActiveRun(r.status)).slice(0, 3);
  const featured = fs
    ? [...fs]
        .sort((a, b) => {
          const attention = (f: Line) =>
            f.active_run
              ? 2
              : pending?.some((r) => r.factory_id === f.id)
                ? 1
                : 0;
          return (
            attention(b) - attention(a) ||
            new Date(b.last_run?.created_at ?? b.created_at).getTime() -
              new Date(a.last_run?.created_at ?? a.created_at).getTime()
          );
        })
        .slice(0, 3)
    : null;
  const hour = new Date().getHours();
  const go = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim()) nav("/fabricas/nova", { state: { prompt: text.trim() } });
  };
  return (
    <div className="home-layout">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">
          {hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite"}.
          Bem-vindo ao seu estúdio.
        </p>
        <span className="hidden text-xs capitalize text-slate-500 md:block">
          {new Date().toLocaleDateString("pt-BR", {
            weekday: "long",
            day: "numeric",
            month: "long",
          })}
        </span>
      </div>
      <section className="home-hero">
        <div className="pointer-events-none absolute -right-20 -top-12 hidden h-[380px] w-[540px] opacity-55 md:block">
          <FactoryCover
            factory={{
              name: "ContentOS",
              description: "",
              config: { theme: "universo" },
            }}
            className="h-full"
          />
        </div>
        <div className="relative max-w-2xl">
          <p className="eyebrow mb-2">Sua imaginação. Um estúdio inteiro.</p>
          <h1>O que você quer produzir hoje?</h1>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-slate-400">
            Dê vida à sua próxima ideia. Descreva o que imagina e crie uma
            fábrica com identidade própria.
          </p>
          <form
            onSubmit={go}
            className="mt-4 flex max-w-2xl flex-col gap-2 rounded-xl border border-white/10 bg-[#081820]/90 p-1.5 sm:flex-row"
          >
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm placeholder:text-slate-500 focus:outline-none"
              aria-label="Sua ideia de fábrica"
              data-testid="home-prompt"
              placeholder="Um canal sobre os mistérios do universo…"
            />
            <button
              className={`${primary} py-2.5`}
              data-testid="home-go"
              disabled={!text.trim()}
            >
              <Icon name="spark" size={16} />
              Criar com IA
            </button>
          </form>
          <p className="mt-2 text-[11px] text-slate-500">
            Da primeira ideia à produção. Você decide o que vai ao ar.
          </p>
        </div>
      </section>
      <div className="grid gap-4 sm:grid-cols-3">
        {[
          {
            icon: "factory",
            value: fs?.length,
            label: "Fábricas no estúdio",
            to: "/fabricas",
          },
          {
            icon: "play",
            value: active?.length,
            label: "Produções em andamento",
            to: "/producoes",
          },
          {
            icon: "check",
            value: pending?.length,
            label: "Aguardando sua revisão",
            to: "/aprovacoes",
          },
        ].map((item) => (
          <Link
            className="stat-tile hover:border-cyan-300/30"
            key={item.to}
            to={item.to}
          >
            <span className="rounded-lg bg-cyan-300/5 p-2 text-cyan-300">
              <Icon name={item.icon} size={18} />
            </span>
            <strong>{item.value ?? "—"}</strong>
            <p className="text-xs text-slate-400">{item.label}</p>
            <Icon name="arrow" size={14} className="ml-auto text-slate-500" />
          </Link>
        ))}
      </div>
      {(factoryError || runError || reviewError) && (
        <Notice tone="error">
          Parte do estúdio não pôde ser atualizada. Estamos tentando reconectar.
        </Notice>
      )}
      <div className="home-projects-layout">
        <section
          className="home-factories"
          aria-labelledby="home-factories-title"
        >
          <div className="section-heading">
            <div>
              <h2 id="home-factories-title">Minhas Fábricas</h2>
            </div>
            <Link className="text-link" to="/fabricas">
              Ver todas <Icon name="arrow" size={15} />
            </Link>
          </div>
          {!fs && !factoryError && <LoadingCards />}
          {fs?.length === 0 && (
            <EmptyState title="Seu estúdio começa com uma ideia">
              Crie uma fábrica e dê a ela um tema, uma voz e uma identidade.
              <Link className="studio-primary mt-5" to="/fabricas/nova">
                <Icon name="plus" size={16} />
                Criar minha primeira fábrica
              </Link>
            </EmptyState>
          )}
          <div className="space-y-4">
            {featured?.map((f) => (
              <FactoryCard
                key={f.id}
                f={f}
                thumbs={thumbs}
                runs={runs ?? []}
                reviews={reviews ?? undefined}
              />
            ))}
          </div>
        </section>
        <section>
          <div className="section-heading">
            <h2>
              {pending?.length || active?.length
                ? "Agora no estúdio"
                : "Atividade do estúdio"}
            </h2>
            <Icon name="clock" size={17} className="text-slate-500" />
          </div>
          <div className={`${card} px-5`}>
            {pending?.slice(0, 2).map((item) => (
              <Link
                key={item.run_id}
                to={`/aprovacoes/${item.run_id}`}
                className="timeline-item"
              >
                <Icon name="check" className="mt-1 text-amber-200" size={17} />
                <div className="min-w-0">
                  <p className="text-xs font-medium text-amber-200">
                    Aguardando sua revisão
                  </p>
                  <p className="mt-1 line-clamp-2 text-sm text-slate-200">
                    {item.title}
                  </p>
                  <p className="mt-1 truncate text-xs text-slate-400">
                    {item.factory_name}
                  </p>
                </div>
                <Icon
                  name="arrow"
                  size={14}
                  className="ml-auto mt-1 text-slate-400"
                />
              </Link>
            ))}
            {active?.slice(0, 2).map((r) => (
              <Link
                key={r.id}
                to={`/producao/${r.id}`}
                className="timeline-item"
              >
                <Icon name="play" className="mt-1 text-cyan-300" size={17} />
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-cyan-200">
                    Em produção
                  </p>
                  <p className="mt-1 truncate text-sm">{r.line_name}</p>
                  <p className="mt-1 text-xs text-slate-400">
                    {r.steps_done} de {r.steps_total} etapas concluídas
                  </p>
                </div>
                <Icon name="arrow" size={14} className="mt-1 text-slate-400" />
              </Link>
            ))}
            {recent?.slice(0, 2).map((r) => (
              <Link
                to={`/producao/${r.id}`}
                key={r.id}
                className="timeline-item"
              >
                <span
                  className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${r.status === "failed" ? "bg-red-300" : "bg-cyan-300"}`}
                />
                <div className="min-w-0">
                  <p className="truncate text-sm text-slate-300">
                    {reviews?.find((a) => a.run_id === r.id)?.title ??
                      r.line_name}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Pill status={r.status} />
                    <span className="text-[10px] text-slate-500">
                      {dateLabel(r.created_at)}
                    </span>
                  </div>
                </div>
              </Link>
            ))}
            {videoRuns?.length === 0 && !active?.length && !pending?.length && (
              <p className="py-8 text-sm leading-relaxed text-slate-500">
                As atividades das suas produções aparecerão aqui.
              </p>
            )}
          </div>
        </section>
      </div>
      <section>
        <div className="section-heading">
          <h2>Produções recentes</h2>
          <Link className="text-link" to="/producoes">
            Ver produções <Icon name="arrow" size={15} />
          </Link>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          {recent?.slice(0, 2).map((r) => (
            <ProductionCard
              key={r.id}
              run={r}
              review={reviews?.find((a) => a.run_id === r.id)}
              thumbnail={thumbs[r.id]}
            />
          ))}
        </div>
        {videoRuns?.length === 0 && (
          <EmptyState icon="play" title="A próxima produção pode ser sua">
            Escolha uma fábrica para começar. O progresso aparece aqui.
          </EmptyState>
        )}
      </section>
    </div>
  );
}

function FactoryCard({
  f,
  thumbs,
  runs,
  reviews,
}: {
  f: Line;
  thumbs: Record<string, string>;
  runs: RunSummary[];
  reviews?: ApprovalItem[];
}) {
  const mine = runs.filter((r) => r.line_id === f.id);
  const last = mine.find((r) => thumbs[r.id]);
  const active = f.active_run ?? mine.find((r) => isActiveRun(r.status));
  const latest = f.last_run ?? mine[0];
  const latestReview = reviews?.find((a) => a.run_id === latest?.id);
  const pendingCount = reviews?.filter(
    (a) => a.factory_id === f.id && a.review.status === "pending",
  ).length;
  const state = active
    ? "Produzindo"
    : f.last_run?.status === "failed"
      ? "Precisa de atenção"
      : f.active
        ? "Automação ligada"
        : "Sob demanda";
  return (
    <Link
      to={`/fabricas/${f.id}`}
      data-testid="factory-card"
      className="factory-project factory-overview group"
    >
      <div className="factory-art relative">
        <FactoryCover
          factory={f}
          image={last ? api.imageUrl(thumbs[last.id]) : undefined}
        />
        <span className="absolute left-4 top-4 flex items-center gap-1.5 rounded-md border border-white/10 bg-[#081820]/80 px-2 py-1 text-[10px] font-medium text-slate-200">
          <span
            className={`h-1.5 w-1.5 rounded-full ${active ? "animate-pulse bg-cyan-300" : state === "Precisa de atenção" ? "bg-amber-300" : "bg-emerald-300"}`}
          />
          {state}
        </span>
        <span className="absolute bottom-3 left-4 rounded bg-[#081820]/85 px-2 py-1 text-[9px] font-semibold uppercase tracking-[.18em] text-white/90">
          YouTube
        </span>
      </div>
      <div className="factory-project-body space-y-3 p-5">
        <div className="flex items-center justify-between gap-3">
          <h3 className="truncate text-base font-semibold group-hover:text-cyan-200">
            {f.name}
          </h3>
          <Icon
            name="arrow"
            size={17}
            className="text-slate-500 group-hover:text-cyan-300"
          />
        </div>
        <p className="line-clamp-2 min-h-10 text-xs leading-relaxed text-slate-400">
          {f.description ||
            String(
              f.config.theme ?? "Uma identidade própria para cada criação.",
            )}
        </p>
        <div className="flex flex-wrap gap-3 border-t border-white/[.06] pt-3 text-[10px] text-slate-500">
          <span className="flex items-center gap-1">
            <Icon name="clock" size={12} />
            {cfgNum(f, "video_minutes")} min
          </span>
          <span>{freqText(cfgNum(f, "frequency_per_week"))}</span>
          <span>{f.products} arquivos</span>
        </div>
        <div className="factory-activity border-t border-white/[.07] pt-3 text-xs">
          {active ? (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-cyan-200">
                  Produção em andamento
                </span>
                <span className="text-slate-400">
                  {active.steps_done}/{active.steps_total} etapas
                </span>
              </div>
              <div
                className="h-1 overflow-hidden rounded bg-white/10"
                role="progressbar"
                aria-label={`Produção de ${f.name}`}
                aria-valuemin={0}
                aria-valuemax={active.steps_total}
                aria-valuenow={active.steps_done}
              >
                <div
                  className="h-full bg-cyan-400"
                  style={{
                    width: `${active.steps_total ? (active.steps_done / active.steps_total) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
          ) : latest ? (
            <>
              <p
                className="truncate font-medium text-slate-300"
                title={latestReview?.title}
              >
                {latestReview?.title ??
                  `Última produção · ${dateLabel(latest.created_at)}`}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Pill status={latest.status} />
                <span className="text-slate-500">
                  {dateLabel(latest.created_at)}
                </span>
              </div>
            </>
          ) : (
            <p className="text-slate-400">Pronta para a primeira produção</p>
          )}
          {!!pendingCount && (
            <p className="mt-2 flex items-center gap-1.5 font-medium text-amber-200">
              <Icon name="check" size={13} />
              {pendingCount}{" "}
              {pendingCount === 1 ? "vídeo aguarda" : "vídeos aguardam"} sua
              revisão
            </p>
          )}
        </div>
      </div>
    </Link>
  );
}

export function Factories() {
  const { data: fs, error } = useFactories();
  const { data: reviews } = usePoll(() => api.approvals("all"), [], 5000);
  const { data: runs } = usePoll(() => api.runs(), [], 4000);
  const [query, setQuery] = useState(""),
    [tab, setTab] = useState("all");
  const thumbs = useThumbs();
  const filtered = fs?.filter(
    (f) =>
      `${f.name} ${f.description}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (tab === "all" || (tab === "producing" ? !!f.active_run : !f.active_run)),
  );
  return (
    <div className="space-y-7">
      <PageHeading
        eyebrow="Seu universo criativo"
        title="Minhas Fábricas"
        description="Cada fábrica, uma identidade. Explore seus projetos e dê vida à próxima produção."
        action={
          <Link
            to="/fabricas/nova"
            className={primary}
            data-testid="new-factory"
          >
            <Icon name="plus" size={17} />
            Criar Fábrica com IA
          </Link>
        }
      />
      <div className="filter-bar">
        <div className="filter-tabs">
          {[
            ["all", `Todas${fs ? ` (${fs.length})` : ""}`],
            ["producing", "Produzindo"],
            ["ready", "Sem produção ativa"],
          ].map(([k, v]) => (
            <button key={k} aria-pressed={tab === k} onClick={() => setTab(k)}>
              {v}
            </button>
          ))}
        </div>
        <label className="search-field">
          <Icon name="search" size={16} />
          <input
            aria-label="Buscar fábricas"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar fábrica…"
          />
        </label>
      </div>
      {error && (
        <Notice tone="error">
          Não foi possível carregar as fábricas. Tentando novamente.
        </Notice>
      )}
      {!fs && !error && <LoadingCards />}
      {filtered?.length === 0 && (
        <EmptyState
          title={
            fs?.length
              ? "Nenhuma fábrica encontrada"
              : "Uma ideia. Infinitas possibilidades."
          }
        >
          {fs?.length
            ? "Experimente outro nome ou filtro."
            : "Descreva o que deseja criar. Seu assistente ajuda a transformar a ideia em uma fábrica."}
          {!fs?.length && (
            <Link to="/fabricas/nova" className="studio-primary mt-5">
              Criar minha primeira fábrica <Icon name="arrow" size={16} />
            </Link>
          )}
        </EmptyState>
      )}
      <div className="factory-grid">
        {filtered?.map((f) => (
          <FactoryCard
            key={f.id}
            f={f}
            thumbs={thumbs}
            runs={runs ?? []}
            reviews={reviews ?? undefined}
          />
        ))}
      </div>
      {!!fs?.length && (
        <p className="text-center text-[11px] text-slate-500">
          Seu estúdio pode crescer com suas ideias.{" "}
          <Link to="/fabricas/nova" className="text-cyan-300">
            Crie uma nova fábrica.
          </Link>
        </p>
      )}
    </div>
  );
}

// ---------- Preview de configuração ----------
function PreviewCard({ rows, title }: { rows: PreviewRow[]; title: string }) {
  return (
    <div className={`${card} p-5`} data-testid="proposal">
      <h3 className="mb-3 text-sm font-semibold text-cyan-300">{title}</h3>
      <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
        {rows.map((r) => (
          <div key={r.label}>
            <dt className="text-xs text-slate-500">{r.label}</dt>
            <dd className="text-sm">{r.value}</dd>
          </div>
        ))}
      </dl>
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
  const proposal =
    !busy &&
    !err &&
    turns[turns.length - 1]?.role === "assistant" &&
    lastReply?.status === "ready"
      ? lastReply.proposal
      : null;

  const send = async (content: string, base: Turn[]) => {
    const next: Turn[] = [...base, { role: "user", content }];
    setTurns(next);
    setText("");
    setBusy(true);
    setErr(null);
    try {
      const reply = await api.chat(
        next.map(({ role, content }) => ({ role, content })),
      );
      const say = [
        reply.message,
        ...(reply.status === "need_info" ? reply.questions : []),
      ]
        .filter(Boolean)
        .join("\n\n");
      setTurns([...next, { role: "assistant", content: say, reply }]);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (initial && !started.current) {
      started.current = true;
      void send(initial, []);
    }
  }, []); // eslint-disable-line
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  const create = async () => {
    if (!proposal) return;
    setCreating(true);
    try {
      const r = await api.createFactory(proposal.config);
      nav(`/fabricas/${r.id}`);
    } catch (e) {
      setErr((e as Error).message);
      setCreating(false);
    }
  };
  return (
    <div className="factory-creation space-y-5">
      <PageHeading
        eyebrow="Uma conversa, um novo começo"
        title="Criar Fábrica com IA"
        description="Conte sua ideia. Juntos, vamos encontrar o tema, a voz e a identidade do seu próximo projeto."
      />
      <div className="flex items-center gap-3 text-[11px] text-slate-500">
        <span className="rounded-full bg-cyan-400/10 px-3 py-1.5 text-cyan-200">
          01 · Sua ideia
        </span>
        <span>—</span>
        <span className={proposal ? "text-cyan-200" : ""}>02 · Identidade</span>
        <span>—</span>
        <span>03 · Sua confirmação</span>
      </div>
      <SetupNotice st={st ?? null} />
      <div className="creation-layout">
        <div className={`${card} conversation-panel space-y-4 p-5`}>
          {turns.length === 0 && !busy && (
            <div className="assistant-welcome">
              <span className="empty-icon">
                <Icon name="spark" size={28} />
              </span>
              <div>
                <h2 className="text-xl font-semibold">
                  Vamos dar forma à sua ideia?
                </h2>
                <p className="mt-3 text-sm leading-relaxed text-slate-300">
                  Conte o que quer produzir, para quem e com qual estilo. Vamos
                  definir juntos a identidade da fábrica.
                </p>
              </div>
            </div>
          )}
          {turns.map((t, i) => (
            <div
              key={i}
              className={`flex ${t.role === "user" ? "justify-end" : ""}`}
            >
              <div
                className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm ${t.role === "user" ? "bg-cyan-400 text-petrol-950" : "bg-petrol-800 text-slate-100"}`}
                data-testid={`msg-${t.role}`}
              >
                {t.content}
              </div>
            </div>
          ))}
          {busy && (
            <div
              role="status"
              className="animate-pulse text-sm text-cyan-200"
              data-testid="thinking"
            >
              Entendendo seu pedido…
            </div>
          )}
          {err && <Notice tone="error">{err}</Notice>}
          <div ref={bottom} />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim() && !busy) void send(text.trim(), turns);
            }}
            className="!mt-auto flex gap-2 pt-5"
          >
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={2}
              className={input}
              aria-label="Mensagem para o assistente criativo"
              data-testid="chat-input"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (text.trim() && !busy) void send(text.trim(), turns);
                }
              }}
              placeholder={
                proposal
                  ? "Quer mudar algo? Escreva aqui (ex.: deixe os vídeos mais curtos)"
                  : "Descreva sua fábrica…"
              }
            />
            <button
              className={primary}
              disabled={busy || !text.trim()}
              data-testid="chat-send"
            >
              Enviar
            </button>
          </form>
        </div>
        <aside className="studio-card creation-suggestions p-5">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Icon name="spark" className="text-cyan-300" />
            Um ponto de partida
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            Escolha uma inspiração e personalize na conversa.
          </p>
          <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
            {[
              {
                name: "Mistérios do universo",
                theme: "universo",
                text: "Quero criar um canal de YouTube sobre mistérios do universo, com vídeos narrados de aproximadamente 10 minutos.",
              },
              {
                name: "Histórias que arrepiam",
                theme: "terror",
                text: "Quero criar um canal de histórias de terror com vídeos de dez minutos, três vezes por semana, narração sombria e imagens cinematográficas.",
              },
              {
                name: "Aprender por curiosidade",
                theme: "ciência",
                text: "Quero um canal educacional sobre ciência para jovens, com vídeos de cinco minutos e linguagem acessível.",
              },
            ].map((e) => (
              <button
                type="button"
                key={e.name}
                className="creation-template"
                onClick={() => setText(e.text)}
              >
                <FactoryCover
                  factory={{
                    name: e.name,
                    description: "",
                    config: { theme: e.theme },
                  }}
                />
                <span className="flex min-w-0 flex-1 items-center justify-between gap-2 px-3 py-4 text-left text-sm font-medium">
                  {e.name}
                  <Icon name="plus" size={15} />
                </span>
              </button>
            ))}
          </div>
          <p className="mt-5 text-xs leading-relaxed text-slate-500">
            Estas são sugestões de tema para vídeos. A fábrica só é criada
            depois da sua confirmação.
          </p>
        </aside>
      </div>
      {proposal && (
        <>
          <PreviewCard rows={proposal.preview} title="Prévia da sua fábrica" />
          <div className="flex flex-wrap gap-3">
            <button
              className={primary}
              onClick={create}
              disabled={creating}
              data-testid="confirm-create"
            >
              Confirmar e criar fábrica
            </button>
            <span className="self-center text-sm text-slate-400">
              ou continue conversando para ajustar.
            </span>
          </div>
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
  const [cur, setCur] = useState<{
    data: Awaited<ReturnType<typeof api.factory>>;
  } | null>(null);
  const [refresh, setRefresh] = useState(0);
  const { data: line, error: lineError } = usePoll(
    () => api.line(id),
    [id, refresh],
    3000,
  );
  const { data: runs, error: runsError } = usePoll(
    () => api.runs(id),
    [id],
    2500,
  );
  const { data: reviews, error: reviewsError } = usePoll(
    () => api.approvals("all"),
    [],
    5000,
  );
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
  const currentRunId = active?.id ?? runs?.[0]?.id;
  const { data: currentRun, error: currentError } = usePoll(
    async () => (currentRunId ? api.run(currentRunId) : null),
    [currentRunId],
    2500,
    (r) => !!r && isActiveRun(r.status),
  );

  const produce = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.produce(id, {
        topic,
        script_text: own ? script : "",
      });
      nav(`/producao/${r.id}`);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const adjust = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setAdjMsg(null);
    setProp(null);
    try {
      setProp(await api.adjustFactory(id, adj));
    } catch (x) {
      setAdjMsg((x as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const apply = async () => {
    if (!prop?.proposal) return;
    setBusy(true);
    setAdjMsg(null);
    try {
      const d = await api.applyFactory(id, prop.proposal.config);
      setCur({ data: d });
      setRefresh((t) => t + 1);
      setProp(null);
      setAdj("");
      setAdjMsg("Ajuste aplicado. Será usado nas próximas produções.");
    } catch (e) {
      setAdjMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const toggleAuto = async () => {
    setBusy(true);
    setMsg(null);
    try {
      await api.lineAction(id, line?.active ? "deactivate" : "activate");
      setRefresh((t) => t + 1);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if ((error && !factory) || (lineError && !line))
    return (
      <Notice tone="error">
        Não foi possível abrir esta fábrica. Verifique a conexão ou volte para
        Minhas Fábricas.
      </Notice>
    );
  if (!factory || !line)
    return <p className="text-sm text-slate-400">Carregando…</p>;
  const mine = (runs ?? []).filter((r) => r.pipeline === "video_youtube");
  return (
    <div className="space-y-6">
      <Link to="/fabricas" className="text-link">
        ← Minhas Fábricas
      </Link>
      <section className="factory-identity studio-card">
        <div className="identity-cover">
          <FactoryCover
            factory={line}
            image={
              mine.find((r) => thumbs[r.id])
                ? api.imageUrl(thumbs[mine.find((r) => thumbs[r.id])!.id])
                : undefined
            }
          />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1
              className="text-2xl font-semibold md:text-3xl"
              data-testid="factory-name"
            >
              {line.name}
            </h1>
            <span className="rounded-full bg-cyan-300/10 px-3 py-1 text-xs text-cyan-200">
              {active
                ? "Em produção"
                : line.interval_minutes
                  ? line.active
                    ? "Automação ligada"
                    : "Automação pausada"
                  : "Sob demanda"}
            </span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-slate-300">
            {line.description || String(line.config.theme ?? "")}
          </p>
          <p className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-400">
            <Icon name="play" size={15} />
            YouTube <span>·</span>
            {cfgNum(line, "video_minutes")} min por vídeo <span>·</span>
            {freqText(cfgNum(line, "frequency_per_week"))}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <a className={ghost} href="#creative-settings">
            <Icon name="settings" size={16} />
            Identidade
          </a>
          <a className={primary} href="#new-production">
            <Icon name="plus" size={16} />
            Nova produção
          </a>
        </div>
      </section>
      <nav className="section-tabs" aria-label="Áreas da fábrica">
        <a href="#factory-production">
          <Icon name="play" size={17} />
          Produção
        </a>
        <a href="#factory-history">
          <Icon name="library" size={17} />
          Conteúdos produzidos
        </a>
        <a href="#creative-settings">
          <Icon name="spark" size={17} />
          Identidade criativa
        </a>
        <a href="#factory-automation">
          <Icon name="clock" size={17} />
          Automação
        </a>
      </nav>
      {(runsError || reviewsError) && (
        <Notice tone="error">
          Não foi possível atualizar parte do histórico desta fábrica.
        </Notice>
      )}
      {!!reviews?.filter(
        (a) => a.factory_id === id && a.review.status === "pending",
      ).length && (
        <Link
          to="/aprovacoes"
          className="flex items-center justify-between gap-4 rounded-xl border border-amber-300/20 bg-amber-300/5 px-5 py-4"
        >
          <span className="flex items-center gap-3 text-sm text-amber-100">
            <Icon name="check" />
            {
              reviews.filter(
                (a) => a.factory_id === id && a.review.status === "pending",
              ).length
            }{" "}
            produção(ões) aguardando sua revisão
          </span>
          <Icon name="arrow" size={18} />
        </Link>
      )}
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,2.2fr)_minmax(300px,1fr)]">
        <div className="min-w-0 space-y-6" id="factory-production">
          {currentError && (
            <Notice tone="error">
              Não foi possível atualizar os materiais da produção.
            </Notice>
          )}
          {currentRun && <ProductionWorkspace run={currentRun} />}
          <div id="new-production" className={`${card} space-y-4 p-5`}>
            <SetupNotice st={st ?? null} />
            <div className="flex items-start gap-3">
              <span className="rounded-lg bg-cyan-300/10 p-2 text-cyan-300">
                <Icon name="spark" />
              </span>
              <div>
                <h2 className="font-semibold">O que vamos produzir agora?</h2>
                <p className="mt-1 text-xs text-slate-400">
                  Traga um tema ou deixe a fábrica encontrar a próxima ideia.
                </p>
              </div>
            </div>
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              className={input}
              aria-label="Tema do novo vídeo"
              data-testid="topic"
              placeholder="Tema do vídeo (opcional — se vazio, a IA escolhe um dentro do tema da fábrica)"
            />
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={own}
                onChange={(e) => setOwn(e.target.checked)}
                data-testid="own-script"
              />
              Tenho meu próprio roteiro (não usa IA)
            </label>
            {own && (
              <textarea
                value={script}
                onChange={(e) => setScript(e.target.value)}
                rows={6}
                className={input}
                aria-label="Seu roteiro"
                data-testid="script-text"
                placeholder="Cole aqui a narração completa…"
              />
            )}
            {msg && <Notice tone="error">{msg}</Notice>}
            <div className="flex flex-wrap items-center gap-3">
              <button
                className={primary}
                onClick={produce}
                disabled={
                  busy ||
                  !!active ||
                  (own ? script.trim().length < 20 : !st?.gemini.configured)
                }
                data-testid="produce"
              >
                <Icon name="play" size={16} />
                {busy ? "Preparando…" : "Produzir vídeo"}
              </button>
              {active && (
                <Link
                  className="text-sm text-cyan-300 hover:underline"
                  to={`/producao/${active.id}`}
                >
                  Há uma produção em andamento →
                </Link>
              )}
            </div>
            {!own && !st?.gemini.configured && (
              <p className="text-xs text-amber-300">
                Sem Gemini configurado, só é possível produzir com roteiro
                próprio.
              </p>
            )}
          </div>
          <div id="factory-history">
            <div className="section-heading">
              <h2>Produções da fábrica</h2>
              <span className="text-xs text-slate-500">Histórico recente</span>
            </div>
            {!runs && !runsError && <LoadingCards count={2} />}
            {runs && mine.length === 0 && (
              <EmptyState icon="play" title="O primeiro vídeo é só o começo">
                Escolha um tema acima para iniciar a história desta fábrica.
              </EmptyState>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              {mine.map((r) => (
                <ProductionCard
                  key={r.id}
                  run={r}
                  review={reviews?.find((a) => a.run_id === r.id)}
                  thumbnail={thumbs[r.id]}
                />
              ))}
            </div>
          </div>
        </div>
        <div className="min-w-0 space-y-5" id="creative-settings">
          <div className={`${card} space-y-4 p-5`}>
            <h2 className="flex items-center gap-2 text-base font-semibold">
              <Icon name="spark" className="text-cyan-300" />
              Assistente da Fábrica
            </h2>
            <div className="assistant-intro">
              <Icon name="spark" size={23} />
              <p>
                Quer ajustar o estilo, a duração ou a voz? Descreva a mudança e
                revise a proposta antes de aplicar.
              </p>
            </div>
            <form onSubmit={adjust} className="space-y-2">
              <input
                value={adj}
                onChange={(e) => setAdj(e.target.value)}
                className={input}
                aria-label="Ajustes na identidade criativa"
                data-testid="adjust-input"
                placeholder="Ex.: deixe os vídeos com 5 minutos e a voz mais lenta"
              />
              <button
                className={ghost}
                disabled={busy || adj.trim().length < 3}
                data-testid="adjust-send"
              >
                Pedir ajuste
              </button>
            </form>
            {adjMsg && (
              <p className="text-sm text-slate-300" data-testid="adjust-msg">
                {adjMsg}
              </p>
            )}
            {prop?.proposal && (
              <div className="space-y-2">
                <p className="text-sm text-slate-300">{prop.message}</p>
                <dl className="space-y-1 text-xs">
                  {prop.proposal.preview.map((r) => (
                    <div key={r.label} className="flex justify-between gap-3">
                      <dt className="text-slate-500">{r.label}</dt>
                      <dd className="text-right">{r.value}</dd>
                    </div>
                  ))}
                </dl>
                <div className="flex gap-2">
                  <button
                    className={primary}
                    disabled={busy}
                    onClick={apply}
                    data-testid="adjust-apply"
                  >
                    Aplicar
                  </button>
                  <button className={ghost} onClick={() => setProp(null)}>
                    Descartar
                  </button>
                </div>
              </div>
            )}
            {prop && !prop.proposal && (
              <p className="text-sm text-amber-200">
                {[prop.message, ...prop.questions].join(" ")}
              </p>
            )}
          </div>
          <PreviewCard rows={factory.preview} title="Identidade criativa" />
          <div
            id="factory-automation"
            className={`${card} space-y-2 p-5 text-sm`}
          >
            <h2 className="font-semibold">Produção automática</h2>
            <p className="text-xs text-slate-400">
              {factory.interval_minutes
                ? `Produz ${freqText(cfgNum(line, "frequency_per_week"))} enquanto estiver ligada.`
                : "Esta fábrica não tem frequência definida: só produz sob demanda."}
            </p>
            <button
              className={ghost}
              onClick={toggleAuto}
              disabled={busy || !factory.interval_minutes}
              data-testid="toggle-auto"
            >
              {line.active ? "Desligar" : "Ligar"} produção automática
            </button>
            <p className="text-xs text-slate-500">
              Custo no mês: {money(line.cost_month)}. A publicação é confirmada
              separadamente.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------- Visualização da produção ----------
export function Production() {
  const { id = "" } = useParams();
  const [refresh, setRefresh] = useState(0);
  const [actionError, setActionError] = useState<string | null>(null);
  const { data: run, error } = usePoll(
    () => api.run(id),
    [id, refresh],
    1500,
    (r: Run) => isActiveRun(r.status) || r.status === "queued",
  );
  const { data: logs } = usePoll(
    () => api.runLogs(id),
    [id, run?.status, refresh],
    2500,
    () => !!run && isActiveRun(run.status),
  );
  const { data: review } = usePoll(
    async () =>
      run?.status === "succeeded" && run.pipeline === "video_youtube"
        ? api.approval(id)
        : null,
    [id, run?.status],
    5000,
    (d) => !!d,
  );
  const [busy, setBusy] = useState(false);
  if (error && !run)
    return <Notice tone="error">Produção não encontrada.</Notice>;
  if (!run) return <p className="text-sm text-slate-400">Carregando…</p>;
  const art = (n: string) => run.artifacts.find((a) => a.filename === n);
  const video = art("video.mp4");
  const exp = run.steps.find((s) => s.name === "export")?.output as {
    title?: string;
    duration_seconds?: number;
  } | null;
  const script = run.steps.find((s) => s.name === "script")?.output as {
    title?: string;
    description?: string;
  } | null;
  const title =
    exp?.title ??
    script?.title ??
    (isActiveRun(run.status)
      ? "Sua ideia está ganhando forma"
      : (run.line_name ?? "Produção"));
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setActionError(null);
    try {
      await fn();
      setRefresh((t) => t + 1);
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const failed = run.steps.find((s) => s.status === "failed");
  const total = run.steps.length,
    done = run.steps.filter((s) => s.status === "succeeded").length;
  const warn = (logs ?? []).filter((l) => l.level === "warn");
  return (
    <div className="production-detail space-y-6">
      <div>
        <Link
          to={run.line_id ? `/fabricas/${run.line_id}` : "/fabricas"}
          className="text-sm text-cyan-300 hover:underline"
        >
          ← {run.line_name ?? "Fábricas"}
        </Link>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-3xl font-semibold" data-testid="prod-title">
            {title}
          </h1>
          <Pill status={run.status} />
        </div>
      </div>
      {actionError && <Notice tone="error">{actionError}</Notice>}
      {error && (
        <Notice tone="error">Não foi possível atualizar esta produção.</Notice>
      )}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,2.4fr)_minmax(280px,1fr)]">
        <div className="space-y-4">
          {video ? (
            <div className={`${card} overflow-hidden`}>
              <video
                controls
                preload="metadata"
                className="aspect-video w-full bg-black"
                src={api.imageUrl(video.id)}
                poster={
                  art("miniatura.jpg")
                    ? api.imageUrl(art("miniatura.jpg")!.id)
                    : undefined
                }
                data-testid="player"
              />
              <div className="flex flex-wrap items-center gap-3 p-4">
                <a
                  className={primary}
                  href={api.downloadUrl(video.id)}
                  data-testid="download"
                >
                  Baixar MP4
                </a>
                {run.pipeline === "video_youtube" && (
                  <Link
                    className={ghost}
                    to={`/aprovacoes/${run.id}`}
                    data-testid="go-review"
                  >
                    Revisar e aprovar
                  </Link>
                )}
                {art("legendas.srt") && (
                  <a
                    className={ghost}
                    href={api.downloadUrl(art("legendas.srt")!.id)}
                  >
                    Baixar legendas (.srt)
                  </a>
                )}
                {art("metadados.json") && (
                  <a
                    className={ghost}
                    href={api.downloadUrl(art("metadados.json")!.id)}
                  >
                    Metadados e créditos
                  </a>
                )}
                <span className="text-xs text-slate-400">
                  {exp?.duration_seconds
                    ? `${Math.round(exp.duration_seconds)} s · `
                    : ""}
                  {(video.size / 1e6).toFixed(1)} MB
                </span>
              </div>
            </div>
          ) : (
            <div
              className={`${card} flex aspect-video flex-col items-center justify-center gap-3 p-6 text-center`}
            >
              {isActiveRun(run.status) ? (
                <>
                  <div className="h-10 w-10 animate-spin rounded-full border-4 border-petrol-600 border-t-cyan-400" />
                  <p className="text-sm text-slate-300">
                    {STEP_LABELS[
                      run.steps.find(
                        (s) =>
                          s.status === "running" || s.status === "retrying",
                      )?.name ?? ""
                    ] ?? "Preparando…"}
                  </p>
                </>
              ) : (
                <p className="text-sm text-slate-400">
                  {run.status === "failed"
                    ? "A produção não terminou."
                    : "Sem vídeo."}
                </p>
              )}
            </div>
          )}
          {script?.description && (
            <div className={`${card} p-5`}>
              <h2 className="mb-3 font-semibold">Sobre esta produção</h2>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-400">
                {script.description}
              </p>
            </div>
          )}
          <p className="text-xs text-slate-500">
            Criada em {new Date(run.created_at).toLocaleString("pt-BR")} ·{" "}
            {run.line_name ?? "Produção independente"}
          </p>
          {run.status === "failed" && (
            <Notice tone="error">
              <strong>
                Falhou
                {failed
                  ? ` em “${STEP_LABELS[failed.name] ?? failed.name}”`
                  : ""}
                :
              </strong>{" "}
              {run.error}
              <div className="mt-3">
                <button
                  className={ghost}
                  disabled={busy}
                  onClick={() => act(() => api.resume(id))}
                  data-testid="resume"
                >
                  Retomar de onde parou
                </button>
              </div>
            </Notice>
          )}
          {warn.map((l, i) => (
            <Notice key={i}>{l.message}</Notice>
          ))}
        </div>
        <div className="space-y-4">
          <div className={`${card} p-5`}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-semibold">
                <Icon name="factory" size={17} className="text-cyan-300" />
                Etapas da produção
              </h2>
              <span className="text-xs text-slate-400">
                {done}/{total}
              </span>
            </div>
            <div className="mb-4 h-1.5 overflow-hidden rounded bg-petrol-800">
              <div
                className="h-full bg-cyan-400 transition-all"
                style={{ width: `${total ? (done / total) * 100 : 0}%` }}
              />
            </div>
            <ol className="space-y-3" data-testid="steps">
              {run.steps.map((s) => (
                <li key={s.name} className="flex gap-3 text-sm">
                  <span
                    className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs ${s.status === "succeeded" ? "bg-emerald-400 text-petrol-950" : s.status === "failed" ? "bg-red-400 text-petrol-950" : s.status === "running" || s.status === "retrying" ? "animate-pulse bg-cyan-400 text-petrol-950" : "bg-petrol-700 text-slate-400"}`}
                  >
                    {s.status === "succeeded"
                      ? "✓"
                      : s.status === "failed"
                        ? "!"
                        : s.position}
                  </span>
                  <div>
                    <div
                      className={s.status === "pending" ? "text-slate-500" : ""}
                    >
                      {STEP_LABELS[s.name] ?? s.name}
                    </div>
                    {s.message && (
                      <div className="text-xs text-slate-400">{s.message}</div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
            {isActiveRun(run.status) && (
              <button
                className={`${ghost} mt-4`}
                disabled={busy || run.cancel_requested}
                onClick={() => act(() => api.cancel(id))}
              >
                {run.cancel_requested ? "Cancelando…" : "Cancelar produção"}
              </button>
            )}
            {run.status === "cancelled" && (
              <button
                className={`${ghost} mt-4`}
                disabled={busy}
                onClick={() => act(() => api.resume(id))}
              >
                Retomar produção
              </button>
            )}
          </div>
          {review && (
            <div className={`${card} space-y-3 p-5`}>
              <h2 className="font-semibold">Revisão e publicação</h2>
              <p className="text-sm text-slate-300">
                {
                  {
                    pending: "Aguardando seu parecer",
                    approved: "Produção aprovada",
                    changes_requested: "Alterações solicitadas",
                    rejected: "Produção rejeitada",
                  }[review.review.status]
                }
              </p>
              {review.publication && (
                <div className="space-y-2 text-xs text-slate-400">
                  <p>
                    YouTube ·{" "}
                    {review.publication.channel_title ?? "Canal conectado"}
                  </p>
                  <p>
                    {{
                      preparing: "Preparando envio",
                      uploading: "Enviando",
                      succeeded: "Enviado como privado",
                      failed: "Falha no envio",
                      uncertain: "Verificação necessária",
                    }[review.publication.status] ?? review.publication.status}
                  </p>
                  {review.publication.url && (
                    <a
                      className="text-link"
                      href={review.publication.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Abrir no YouTube <Icon name="arrow" size={14} />
                    </a>
                  )}
                </div>
              )}
              <Link to={`/aprovacoes/${id}`} className="text-link">
                Abrir revisão <Icon name="arrow" size={14} />
              </Link>
              <p className="text-xs text-slate-500">
                Aprovar não publica automaticamente.
              </p>
            </div>
          )}
          <div className={`${card} p-5 text-sm`}>
            <h2 className="mb-2 font-semibold">Custos</h2>
            <p className="text-slate-300" data-testid="cost">
              {money(run.cost)}
            </p>
            <p className="text-xs text-slate-500">
              Valor registrado para esta produção. Consulte as informações
              detalhadas nas ferramentas avançadas.
            </p>
          </div>
        </div>
      </div>
      <ProductionAssets run={run} />
      {logs && logs.length > 0 && (
        <details className={`${card} p-4 text-xs`}>
          <summary className="cursor-pointer text-sm text-slate-300">
            Registro detalhado
          </summary>
          <ul className="mt-3 space-y-1 font-mono text-slate-400">
            {logs.map((l, i) => (
              <li
                key={i}
                className={
                  l.level === "error"
                    ? "text-red-300"
                    : l.level === "warn"
                      ? "text-amber-300"
                      : ""
                }
              >
                {new Date(l.created_at).toLocaleTimeString("pt-BR")}{" "}
                {l.step_name ? `[${l.step_name}] ` : ""}
                {l.message}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
