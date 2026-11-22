import { useState } from "react";
import { Link } from "react-router-dom";
import { api, RunSummary, ApprovalItem } from "../api";
import { usePoll } from "../hooks";
import { FactoryFilter, ViewToggle } from "../components/CollectionControls";
import { PublicationCalendar } from "../components/PublicationCalendar";
import { ArtifactPreview, artifactKind } from "../components/ProductionAssets";
import { isActiveRun, size, fmt } from "../ui";
import { Pill, Notice, card, ghost } from "../studio";
import {
  FactoryCover,
  EmptyState,
  Icon,
  LoadingCards,
  PageHeading,
  dateLabel,
} from "../components/StudioVisuals";

const reviewLabels: Record<string, string> = {
  pending: "Aguardando revisão",
  approved: "Aprovada",
  changes_requested: "Alterações solicitadas",
  rejected: "Rejeitada",
};

const reviewClasses = {
  pending: "review-pending",
  approved: "review-approved",
  changes_requested: "review-changes_requested",
  rejected: "review-rejected",
};

export function ProductionCard({
  run,
  review,
  thumbnail,
}: {
  run: RunSummary;
  review?: ApprovalItem;
  thumbnail?: string;
}) {
  const percent = run.steps_total
    ? Math.round((run.steps_done / run.steps_total) * 100)
    : 0;
  return (
    <Link
      to={
        run.pipeline === "video_youtube"
          ? `/producao/${run.id}`
          : `/execucoes/${run.id}`
      }
      className="factory-project production-card"
      data-testid="production-card"
    >
      <div className="production-card-art relative">
        <FactoryCover
          factory={{
            name: run.line_name ?? run.pipeline,
            description: "",
            config: {},
          }}
          image={
            review?.thumbnail_artifact_id
              ? api.imageUrl(review.thumbnail_artifact_id)
              : thumbnail
                ? api.imageUrl(thumbnail)
                : undefined
          }
        />
        <span className="media-type">
          <Icon name="play" size={12} />
          {run.trigger === "pilot" ? "Vídeo-piloto" : run.pipeline === "video_youtube" ? "Vídeo" : "Produção"}
        </span>
        <span className="media-status">
          {review && run.status === "succeeded" ? (
            <span className={reviewClasses[review.review.status]}>
              {reviewLabels[review.review.status]}
            </span>
          ) : (
            <Pill status={run.status} />
          )}
        </span>
      </div>
      <div className="production-card-body space-y-3 p-4">
        {run.standard_version && <p className="text-xs text-cyan-200">Padrão v{run.standard_version} · {run.format === "vertical" ? "9:16" : "16:9"}</p>}
        <h3 className="line-clamp-2 text-base font-semibold">
          {review?.title ?? run.line_name ?? "Produção"}
        </h3>
        <p className="flex items-center gap-2 truncate text-xs text-slate-400">
          <Icon name="factory" size={14} />
          {run.line_name ?? "Laboratório"}
        </p>
        <div className="flex items-center justify-between gap-3 text-xs">
          <span className="text-slate-400">{dateLabel(run.created_at)}</span>
          <span className="text-cyan-200">
            {run.steps_done}/{run.steps_total} etapas · {percent}%
          </span>
        </div>
        <div
          className="progress-track"
          role="progressbar"
          aria-valuenow={run.steps_done}
          aria-valuemin={0}
          aria-valuemax={run.steps_total}
          aria-label="Etapas concluídas"
        >
          <div style={{ width: `${percent}%` }} />
        </div>
        <span className="studio-ghost w-full py-2 text-xs">
          <Icon name="eye" size={15} />
          Ver produção <Icon name="arrow" size={14} />
        </span>
      </div>
    </Link>
  );
}

export function Productions() {
  const { data, error } = usePoll(() => api.runs(), [], 4000);
  const { data: reviews, error: reviewError } = usePoll(
    () => api.approvals("all"),
    [],
    6000,
  );
  const { data: artifacts } = usePoll(() => api.artifacts(), [], 6000);
  const [tab, setTab] = useState("all"),
    [query, setQuery] = useState(""),
    [factory, setFactory] = useState("all"),
    [sort, setSort] = useState("newest"),
    [view, setView] = useState<"grid" | "list">("grid");
  const video = data?.filter((r) => r.pipeline === "video_youtube");
  const options = Array.from(
    new Map(
      (video ?? [])
        .filter((r) => r.line_id)
        .map((r) => [
          r.line_id!,
          { id: r.line_id!, name: r.line_name ?? "Fábrica" },
        ]),
    ).values(),
  );
  const matches = (r: RunSummary, key: string) =>
    key === "all" ||
    (key === "active"
      ? isActiveRun(r.status)
      : key === "pending"
        ? reviews?.some(
            (a) => a.run_id === r.id && a.review.status === "pending",
          )
        : key === "failed"
          ? ["failed", "cancelled"].includes(r.status)
          : r.status === key);
  const filtered = video?.filter(
    (r) =>
      (factory === "all" || r.line_id === factory) &&
      `${r.line_name ?? ""} ${reviews?.find((a) => a.run_id === r.id)?.title ?? ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const items = filtered
    ?.filter((r) => matches(r, tab))
    .sort((a, b) =>
      sort === "oldest"
        ? a.created_at.localeCompare(b.created_at)
        : sort === "name"
          ? (a.line_name ?? "").localeCompare(b.line_name ?? "", "pt-BR")
          : b.created_at.localeCompare(a.created_at),
    );
  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Da ideia ao conteúdo"
        title="Produções"
        description="Acompanhe cada conteúdo, da primeira etapa à revisão final."
        action={
          <Link to="/fabricas" className="studio-primary">
            <Icon name="plus" size={17} />
            Nova produção
          </Link>
        }
      />
      <div className="filter-tabs w-fit">
        {[
          ["all", "Todas"],
          ["active", "Em andamento"],
          ["pending", "Aguardando revisão"],
          ["succeeded", "Concluídas"],
          ["failed", "Atenção"],
        ].map(([key, label]) => (
          <button
            key={key}
            aria-pressed={tab === key}
            onClick={() => setTab(key)}
          >
            {label}{" "}
            <span className="tab-count">
              {filtered && (key !== "pending" || reviews)
                ? filtered.filter((r) => matches(r, key)).length
                : "—"}
            </span>
          </button>
        ))}
      </div>
      <div className="filter-bar">
        <FactoryFilter
          value={factory}
          onChange={setFactory}
          options={options}
        />
        <label className="collection-select">
          <Icon name="clock" size={16} />
          <select
            value={sort}
            aria-label="Ordenar produções"
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="newest">Mais recentes</option>
            <option value="oldest">Mais antigas</option>
            <option value="name">Nome da fábrica</option>
          </select>
        </label>
        <label className="search-field flex-1">
          <Icon name="search" size={16} />
          <input
            className="w-full"
            aria-label="Buscar produções"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar produção…"
          />
        </label>
        <ViewToggle value={view} onChange={setView} />
      </div>
      {error && (
        <Notice tone="error">
          Não foi possível atualizar as produções. Tentando novamente.
        </Notice>
      )}
      {reviewError && (
        <Notice tone="error">
          Não foi possível atualizar os pareceres de revisão.
        </Notice>
      )}
      {!data && !error && <LoadingCards />}
      <div className="collection-layout">
        <div className="min-w-0">
          {items?.length === 0 && (
            <EmptyState
              icon="play"
              title={
                video?.length
                  ? "Nenhuma produção encontrada"
                  : "Sua próxima ideia começa aqui"
              }
            >
              {video?.length
                ? "Ajuste a busca ou os filtros para encontrar outro conteúdo."
                : "Abra uma fábrica para iniciar sua primeira produção."}
            </EmptyState>
          )}
          <div
            className={view === "grid" ? "production-grid" : "production-list"}
          >
            {items?.map((r) => (
              <ProductionCard
                key={r.id}
                run={r}
                review={reviews?.find((a) => a.run_id === r.id)}
                thumbnail={
                  artifacts?.find(
                    (a) => a.run_id === r.id && a.filename === "miniatura.jpg",
                  )?.id
                }
              />
            ))}
          </div>
        </div>
        <aside className="space-y-5">
          <section className="studio-card p-5">
            <h2 className="summary-title">
              <Icon name="play" />
              Resumo da produção
            </h2>
            <p className="mt-2 text-xs text-slate-500">
              Histórico recente de todas as fábricas
            </p>
            <dl className="summary-list">
              {[
                ["active", "Em andamento"],
                ["pending", "Aguardando revisão"],
                ["succeeded", "Concluídas"],
                ["failed", "Precisam de atenção"],
              ].map(([key, label]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>
                    {video && (key !== "pending" || reviews)
                      ? video.filter((r) => matches(r, key)).length
                      : "—"}
                  </dd>
                </div>
              ))}
            </dl>
            <Link to="/aprovacoes" className="studio-ghost mt-4 w-full text-xs">
              Revisar conteúdos <Icon name="arrow" size={15} />
            </Link>
          </section>
          <section className="studio-card px-5 py-4">
            <h2 className="summary-title mb-1">
              <Icon name="clock" />
              Atividade recente
            </h2>
            {!video && !error && (
              <p className="py-4 text-sm text-slate-400">
                Carregando atividade…
              </p>
            )}
            {video?.length === 0 && (
              <p className="py-4 text-sm text-slate-400">
                As primeiras produções aparecerão aqui.
              </p>
            )}
            {video?.slice(0, 4).map((r) => (
              <Link
                className="timeline-item"
                key={r.id}
                to={`/producao/${r.id}`}
              >
                <Icon
                  name={r.status === "succeeded" ? "check" : "play"}
                  size={16}
                  className="mt-1 text-cyan-300"
                />
                <span className="min-w-0">
                  <span className="block truncate text-sm">
                    {reviews?.find((a) => a.run_id === r.id)?.title ??
                      r.line_name}
                  </span>
                  <span className="mt-2 flex flex-wrap items-center gap-2">
                    <Pill status={r.status} />
                    <span className="text-[11px] text-slate-500">
                      {dateLabel(r.created_at)}
                    </span>
                  </span>
                </span>
              </Link>
            ))}
          </section>
        </aside>
      </div>
      <p className="text-xs text-slate-500">
        O progresso acompanha a produção. A revisão e a publicação são etapas
        confirmadas separadamente.
      </p>
    </div>
  );
}

export function Publications() {
  const { data: youtube, error: youtubeError } = usePoll(
    () => api.ytStatus(),
    [],
    10000,
  );
  const { data, error } = usePoll(() => api.approvals("all"), [], 5000);
  const [tab, setTab] = useState("all"),
    [view, setView] = useState("list"),
    [query, setQuery] = useState(""),
    [factory, setFactory] = useState("all");
  const eligible = data?.filter(
    (a) => a.publication || a.review.status === "approved",
  );
  const options = Array.from(
    new Map(
      (eligible ?? [])
        .filter((a) => a.factory_id)
        .map((a) => [
          a.factory_id!,
          { id: a.factory_id!, name: a.factory_name ?? "Fábrica" },
        ]),
    ).values(),
  );
  const matches = (a: ApprovalItem, key: string) =>
    key === "all" ||
    (key === "pending"
      ? !a.publication ||
        ["preparing", "uploading"].includes(a.publication.status)
      : key === "failed"
        ? ["failed", "uncertain"].includes(a.publication?.status ?? "")
        : a.publication?.status === key);
  const items = eligible?.filter(
    (a) =>
      matches(a, tab) &&
      (factory === "all" || a.factory_id === factory) &&
      `${a.title} ${a.factory_name}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const labels: Record<string, string> = {
    preparing: "Preparando envio",
    uploading: "Enviando",
    succeeded: "Enviado como privado",
    failed: "Falha no envio",
    uncertain: "Verificação necessária",
  };
  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Mesa editorial"
        title="Publicações"
        description="Revise o que está pronto e acompanhe os envios reais ao seu canal."
        action={
          <Link to="/configuracoes" className="studio-ghost">
            <Icon name="settings" size={17} />
            Gerenciar canal
          </Link>
        }
      />
      <div className="editorial-note">
        <Icon name="check" size={18} />
        <p>
          <strong>Aprovar não publica.</strong> Cada envio ao YouTube exige sua
          confirmação e permanece privado.
        </p>
      </div>
      <div className="filter-tabs w-fit">
        {[
          ["all", "Todas"],
          ["pending", "Aguardando envio"],
          ["succeeded", "Enviadas"],
          ["failed", "Atenção"],
        ].map(([key, label]) => (
          <button
            key={key}
            aria-pressed={tab === key}
            onClick={() => setTab(key)}
          >
            {label}
            <span className="tab-count">
              {eligible ? eligible.filter((a) => matches(a, key)).length : "—"}
            </span>
          </button>
        ))}
      </div>
      <div className="filter-bar">
        <FactoryFilter
          value={factory}
          onChange={setFactory}
          options={options}
        />
        <label className="search-field flex-1">
          <Icon name="search" size={16} />
          <input
            className="w-full"
            aria-label="Buscar publicações"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar conteúdo…"
          />
        </label>
        <div
          className="view-toggle"
          role="group"
          aria-label="Visualização editorial"
        >
          <button
            aria-pressed={view === "list"}
            onClick={() => setView("list")}
          >
            <Icon name="list" size={17} />
            Lista
          </button>
          <button
            aria-pressed={view === "calendar"}
            onClick={() => setView("calendar")}
          >
            <Icon name="calendar" size={17} />
            Calendário
          </button>
        </div>
      </div>
      {error && (
        <Notice tone="error">Não foi possível carregar as publicações.</Notice>
      )}
      {!data && !error && <LoadingCards />}
      <div className="collection-layout">
        <div className="min-w-0 space-y-4">
          {view === "calendar" ? (
            <PublicationCalendar items={items ?? []} />
          ) : items?.length === 0 ? (
            <EmptyState icon="publish" title="Nenhuma publicação por aqui">
              Os conteúdos aprovados e os envios reais aparecerão nesta área.
              <Link
                to="/aprovacoes"
                className="text-link mt-4 flex justify-center"
              >
                Ir para aprovações <Icon name="arrow" size={15} />
              </Link>
            </EmptyState>
          ) : (
            items?.map((a) => (
              <article key={a.run_id} className="studio-card publication-row">
                <div className="publication-art">
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
                </div>
                <div className="min-w-0 flex-1 space-y-2">
                  <p className="text-[10px] uppercase tracking-widest text-slate-400">
                    YouTube ·{" "}
                    {a.publication?.channel_title ??
                      youtube?.channel?.title ??
                      "Canal a confirmar"}
                  </p>
                  <h2 className="text-base font-semibold">
                    {a.publication?.title ?? a.title}
                  </h2>
                  <p className="text-xs text-slate-400">{a.factory_name}</p>
                  <p
                    className={`text-xs font-medium ${["failed", "uncertain"].includes(a.publication?.status ?? "") ? "text-amber-200" : "text-cyan-200"}`}
                  >
                    {a.publication
                      ? (labels[a.publication.status] ?? a.publication.status)
                      : "Aprovada · aguardando confirmação do envio"}
                  </p>
                  {a.publication && (
                    <p className="text-xs text-slate-500">
                      Envio iniciado em {fmt(a.publication.created_at)}
                    </p>
                  )}
                  {a.publication?.error && (
                    <p className="text-xs text-red-200">
                      {a.publication.error}
                    </p>
                  )}
                  {a.publication &&
                    ["preparing", "uploading"].includes(
                      a.publication.status,
                    ) && (
                      <p className="text-xs text-slate-400">
                        {size(a.publication.progress)} enviados
                      </p>
                    )}
                  <div className="flex flex-wrap gap-2 pt-1">
                    <Link
                      className="studio-ghost py-2 text-xs"
                      to={`/aprovacoes/${a.run_id}`}
                    >
                      {a.publication
                        ? "Ver envio e histórico"
                        : "Preparar envio"}
                      <Icon name="arrow" size={14} />
                    </Link>
                    {a.publication?.url && (
                      <a
                        href={a.publication.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-link"
                      >
                        Abrir no YouTube <Icon name="arrow" size={14} />
                      </a>
                    )}
                  </div>
                </div>
              </article>
            ))
          )}
        </div>
        <aside className="space-y-5">
          <section className="studio-card p-5">
            <h2 className="summary-title">
              <Icon name="publish" />
              Canal de publicação
            </h2>
            <div className="my-5 space-y-3 border-y border-white/10 py-4">
              <div className="flex flex-wrap justify-between gap-2">
                <strong className="text-sm">YouTube</strong>
                <span className="text-xs text-cyan-200">
                  {youtube
                    ? {
                        connected: "Conectado",
                        revoked: "Acesso revogado",
                        pending: "Não conectado",
                        unconfigured: "Não configurado",
                      }[youtube.status]
                    : youtubeError
                      ? "Consulta indisponível"
                      : "Consultando…"}
                </span>
              </div>
              {youtube?.channel && (
                <p className="text-sm text-slate-300">
                  {youtube.channel.title}
                </p>
              )}
            </div>
            <p className="text-xs leading-relaxed text-slate-400">
              A integração disponível envia vídeos como privados. A aprovação
              humana e a confirmação do envio são independentes.
            </p>
            <Link
              to="/configuracoes"
              className="studio-ghost mt-5 w-full text-xs"
            >
              Gerenciar conexão <Icon name="arrow" size={15} />
            </Link>
          </section>
          <section className="studio-card p-5">
            <h2 className="summary-title">
              <Icon name="clock" />
              Prontos para o próximo passo
            </h2>
            <p className="mt-3 text-sm text-slate-300">
              {eligible ? eligible.filter((a) => !a.publication).length : "—"}{" "}
              conteúdos aprovados aguardando confirmação.
            </p>
            <p className="mt-3 text-xs leading-relaxed text-slate-500">
              Agendamento editorial ainda não disponível. O calendário consulta
              as datas dos envios registrados.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}

export function StudioLibrary() {
  const { data, error } = usePoll(() => api.artifacts(), [], 6000);
  const { data: runs, error: originError } = usePoll(
    () => api.runs(),
    [],
    6000,
  );
  const [tab, setTab] = useState("all"),
    [query, setQuery] = useState(""),
    [factory, setFactory] = useState("all"),
    [period, setPeriod] = useState("all"),
    [sort, setSort] = useState("newest"),
    [view, setView] = useState<"grid" | "list">("grid"),
    [selectedId, setSelectedId] = useState<string | null>(null),
    [visibleCount, setVisibleCount] = useState(12);
  const options = Array.from(
    new Map(
      (runs ?? [])
        .filter((r) => r.line_id)
        .map((r) => [
          r.line_id!,
          { id: r.line_id!, name: r.line_name ?? "Fábrica" },
        ]),
    ).values(),
  );
  const origin = (id: string) => runs?.find((r) => r.id === id);
  const items = data
    ?.filter(
      (a) =>
        (tab === "all" || artifactKind(a.content_type) === tab) &&
        (factory === "all" || origin(a.run_id)?.line_id === factory) &&
        (period === "all" ||
          new Date(a.created_at).getTime() >=
            Date.now() - Number(period) * 86400000) &&
        a.filename.toLowerCase().includes(query.toLowerCase()),
    )
    .sort((a, b) =>
      sort === "oldest"
        ? a.created_at.localeCompare(b.created_at)
        : sort === "name"
          ? a.filename.localeCompare(b.filename, "pt-BR")
          : b.created_at.localeCompare(a.created_at),
    );
  const selected = items?.find((a) => a.id === selectedId) ?? items?.[0];
  const choose = (id: string) => {
    setSelectedId(id);
    if (window.matchMedia("(max-width:1279px)").matches)
      document
        .getElementById("library-preview")
        ?.scrollIntoView({ behavior: "smooth" });
  };
  const poster = (id: string) => {
    const image = data?.find(
      (a) => a.run_id === id && a.filename === "miniatura.jpg",
    );
    return image ? api.imageUrl(image.id) : undefined;
  };
  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Seu acervo criativo"
        title="Biblioteca"
        description="Todos os arquivos reais das suas produções, com a origem e a prévia sempre por perto."
      />
      <div className="filter-tabs w-fit">
        {[
          ["all", "Todos"],
          ["video", "Vídeos"],
          ["image", "Imagens"],
          ["audio", "Áudios"],
          ["file", "Documentos"],
        ].map(([key, label]) => (
          <button
            key={key}
            aria-pressed={tab === key}
            onClick={() => {
              setTab(key);
              setVisibleCount(12);
            }}
          >
            {label}
            <span className="tab-count">
              {data
                ? data.filter(
                    (a) =>
                      key === "all" || artifactKind(a.content_type) === key,
                  ).length
                : "—"}
            </span>
          </button>
        ))}
      </div>
      <div className="filter-bar">
        <FactoryFilter
          value={factory}
          onChange={(v) => {
            setFactory(v);
            setVisibleCount(12);
          }}
          options={options}
          label="Filtrar arquivos por fábrica"
        />
        <label className="collection-select">
          <Icon name="calendar" size={16} />
          <select
            aria-label="Período dos arquivos"
            value={period}
            onChange={(e) => {
              setPeriod(e.target.value);
              setVisibleCount(12);
            }}
          >
            <option value="all">Todas as datas</option>
            <option value="7">Últimos 7 dias</option>
            <option value="30">Últimos 30 dias</option>
          </select>
        </label>
        <label className="collection-select">
          <select
            aria-label="Ordenar arquivos"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="newest">Mais recentes</option>
            <option value="oldest">Mais antigos</option>
            <option value="name">Nome do arquivo</option>
          </select>
        </label>
        <label className="search-field flex-1">
          <Icon name="search" size={16} />
          <input
            className="w-full"
            aria-label="Buscar arquivos"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setVisibleCount(12);
            }}
            placeholder="Buscar na biblioteca…"
          />
        </label>
        <ViewToggle value={view} onChange={setView} />
      </div>
      {error && (
        <Notice tone="error">Não foi possível carregar os arquivos.</Notice>
      )}
      {originError && (
        <Notice tone="error">
          Não foi possível atualizar a origem dos arquivos.
        </Notice>
      )}
      {!data && !error && <LoadingCards />}
      {items?.length === 0 && (
        <EmptyState
          icon="library"
          title={
            data?.length
              ? "Nenhum arquivo encontrado"
              : "Um espaço para suas criações"
          }
        >
          {data?.length
            ? "Ajuste os filtros ou busque por outro nome."
            : "Os arquivos das suas produções aparecerão aqui, prontos para visualizar e baixar."}
        </EmptyState>
      )}
      <div className="collection-layout">
        <div className={view === "grid" ? "library-grid" : "library-list"}>
          {items?.slice(0, visibleCount).map((a) => (
            <article
              key={a.id}
              className="studio-card library-file"
              data-selected={selected?.id === a.id}
            >
              <div className="library-file-preview">
                <ArtifactPreview artifact={a} poster={poster(a.run_id)} />
              </div>
              <div className="library-file-body space-y-3 p-4">
                <h2 className="truncate text-sm font-medium" title={a.filename}>
                  {a.filename}
                </h2>
                <p className="truncate text-xs text-slate-400">
                  <Icon name="factory" size={13} className="mr-1 inline" />
                  {origin(a.run_id)?.line_name ??
                    `Produção ${a.run_id.slice(0, 8)}`}
                </p>
                <p className="text-xs text-slate-500">
                  {size(a.size)} · {dateLabel(a.created_at)}
                </p>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <button
                    className="text-link"
                    aria-pressed={selected?.id === a.id}
                    onClick={() => choose(a.id)}
                  >
                    Detalhes
                  </button>
                  <Link className="text-link" to={`/execucoes/${a.run_id}`}>
                    Ver origem
                  </Link>
                  <a
                    className="text-link"
                    href={api.downloadUrl(a.id)}
                    aria-label={`Baixar ${a.filename}`}
                  >
                    <Icon name="download" size={16} />
                  </a>
                </div>
              </div>
            </article>
          ))}
        </div>
        {selected && (
          <aside
            id="library-preview"
            className="studio-card library-inspector overflow-hidden"
          >
            <div className="library-inspector-preview">
              <ArtifactPreview
                artifact={selected}
                poster={poster(selected.run_id)}
              />
            </div>
            <div className="space-y-5 p-5">
              <h2 className="break-all text-lg font-semibold">
                {selected.filename}
              </h2>
              <dl className="inspector-facts">
                <div>
                  <dt>Origem</dt>
                  <dd>
                    {origin(selected.run_id)?.line_name ??
                      `Produção ${selected.run_id.slice(0, 8)}`}
                  </dd>
                </div>
                <div>
                  <dt>Tipo</dt>
                  <dd>{selected.content_type}</dd>
                </div>
                <div>
                  <dt>Criado em</dt>
                  <dd>{fmt(selected.created_at)}</dd>
                </div>
                <div>
                  <dt>Tamanho</dt>
                  <dd>{size(selected.size)}</dd>
                </div>
              </dl>
              <div className="flex flex-wrap gap-2">
                <a
                  className="studio-primary text-xs"
                  href={api.imageUrl(selected.id)}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Icon name="eye" size={15} />
                  Visualizar
                </a>
                <a
                  className="studio-ghost text-xs"
                  href={api.downloadUrl(selected.id)}
                >
                  <Icon name="download" size={15} />
                  Baixar
                </a>
              </div>
              <Link className="text-link" to={`/execucoes/${selected.run_id}`}>
                Abrir produção de origem <Icon name="arrow" size={14} />
              </Link>
              <div className="border-t border-white/10 pt-4">
                <h3 className="mb-3 text-sm font-semibold">
                  Da mesma produção
                </h3>
                <div className="grid grid-cols-4 gap-2">
                  {data
                    ?.filter(
                      (a) =>
                        a.run_id === selected.run_id && a.id !== selected.id,
                    )
                    .slice(0, 4)
                    .map((a) => (
                      <button
                        key={a.id}
                        className="related-asset"
                        onClick={() => {
                          setTab("all");
                          setQuery("");
                          setPeriod("all");
                          choose(a.id);
                        }}
                        aria-label={`Selecionar ${a.filename}`}
                        title={a.filename}
                      >
                        {artifactKind(a.content_type) === "image" ? (
                          <img src={api.imageUrl(a.id)} alt="" />
                        ) : (
                          <Icon
                            name={
                              artifactKind(a.content_type) === "audio"
                                ? "audio"
                                : artifactKind(a.content_type) === "video"
                                  ? "play"
                                  : "file"
                            }
                            size={20}
                          />
                        )}
                      </button>
                    ))}
                </div>
              </div>
            </div>
          </aside>
        )}
      </div>
      {!!items?.length && visibleCount < items.length && (
        <div className="flex flex-wrap items-center justify-center gap-4 pt-3">
          <span className="text-xs text-slate-400">
            {Math.min(visibleCount, items.length)} de {items.length} arquivos
            recentes
          </span>
          <button
            className="studio-ghost text-xs"
            onClick={() => setVisibleCount((n) => n + 12)}
          >
            Carregar mais
          </button>
        </div>
      )}
    </div>
  );
}
