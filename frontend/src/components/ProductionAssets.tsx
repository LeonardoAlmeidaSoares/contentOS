import { useState } from "react";
import { api, Artifact, Run } from "../api";
import { size } from "../ui";
import { EmptyState, Icon } from "./StudioVisuals";

export const artifactKind = (type: string) =>
  type.startsWith("image/")
    ? "image"
    : type.startsWith("video/")
      ? "video"
      : type.startsWith("audio/")
        ? "audio"
        : "file";
export function ArtifactPreview({
  artifact,
  poster,
}: {
  artifact: Artifact;
  poster?: string;
}) {
  const kind = artifactKind(artifact.content_type);
  if (kind === "image")
    return (
      <img
        src={api.imageUrl(artifact.id)}
        alt={artifact.filename}
        loading="lazy"
        className="h-full w-full object-contain"
      />
    );
  if (kind === "video")
    return (
      <video
        controls
        preload="metadata"
        src={api.imageUrl(artifact.id)}
        poster={poster}
        className="h-full w-full"
        aria-label={`Prévia de ${artifact.filename}`}
      />
    );
  if (kind === "audio")
    return (
      <div className="w-full px-3">
        <p className="mb-4 text-center text-xs text-slate-400">
          Narração & áudio
        </p>
        <audio
          controls
          preload="metadata"
          src={api.imageUrl(artifact.id)}
          className="w-full"
          aria-label={`Prévia de ${artifact.filename}`}
        />
      </div>
    );
  return (
    <div className="flex flex-col items-center gap-3 text-slate-400">
      <Icon name="file" size={40} />
      <span className="text-xs uppercase tracking-widest">
        {artifact.filename.split(".").pop()}
      </span>
    </div>
  );
}

export function ProductionAssets({ run }: { run: Run }) {
  const [tab, setTab] = useState("all");
  const groups = [
    { key: "all", label: "Materiais", icon: "library" },
    { key: "script", label: "Roteiro", icon: "file" },
    { key: "image", label: "Imagens", icon: "library" },
    { key: "audio", label: "Narração", icon: "audio" },
    { key: "file", label: "Documentos", icon: "file" },
  ];
  const output = run.steps.find((s) => s.name === "script")?.output;
  const sections = Array.isArray(output?.sections)
    ? (output.sections as {
        heading?: string;
        text?: string;
        scenes?: { narration?: string }[];
      }[])
    : [];
  const script = sections
    .map((s) =>
      [s.heading, s.text, ...(s.scenes ?? []).map((c) => c.narration)]
        .filter(Boolean)
        .join("\n\n"),
    )
    .join("\n\n");
  const files = run.artifacts.filter(
    (a) => tab === "all" || artifactKind(a.content_type) === tab,
  );
  return (
    <section
      className="studio-card p-4 md:p-5"
      aria-label="Materiais e arquivos da produção"
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Icon name="library" className="text-cyan-300" />
          Materiais do conteúdo
        </h2>
        <span className="text-xs text-slate-400">
          {run.artifacts.length} arquivos
        </span>
      </div>
      <div className="filter-tabs mb-5 w-fit">
        {groups.map((g) => (
          <button
            key={g.key}
            aria-pressed={tab === g.key}
            onClick={() => setTab(g.key)}
            className="inline-flex items-center gap-2"
          >
            <Icon name={g.icon} size={15} />
            {g.label}
            {["image", "audio", "file"].includes(g.key) && (
              <span className="text-[10px]">
                (
                {
                  run.artifacts.filter(
                    (a) => artifactKind(a.content_type) === g.key,
                  ).length
                }
                )
              </span>
            )}
          </button>
        ))}
      </div>
      {tab === "script" ? (
        script ? (
          <div className="script-reader">
            <p className="mb-4 text-xs font-medium uppercase tracking-widest text-cyan-200">
              Roteiro da produção
            </p>
            <p className="whitespace-pre-wrap text-sm leading-7 text-slate-200">
              {script}
            </p>
          </div>
        ) : (
          <EmptyState icon="file" title="Nenhum roteiro disponível">
            O roteiro aparece aqui quando for gerado.
          </EmptyState>
        )
      ) : files.length ? (
        <div className="asset-grid">
          {files.map((a) => (
            <article key={a.id} className="asset-tile">
              <a
                href={api.imageUrl(a.id)}
                target="_blank"
                rel="noreferrer"
                className="asset-thumbnail"
                aria-label={`Visualizar ${a.filename}`}
              >
                {artifactKind(a.content_type) === "image" ? (
                  <img
                    src={api.imageUrl(a.id)}
                    alt={a.filename}
                    loading="lazy"
                  />
                ) : (
                  <Icon
                    name={
                      artifactKind(a.content_type) === "audio"
                        ? "audio"
                        : artifactKind(a.content_type) === "video"
                          ? "play"
                          : "file"
                    }
                    size={32}
                  />
                )}
              </a>
              <div className="p-3">
                <p className="truncate text-xs font-medium" title={a.filename}>
                  {a.filename}
                </p>
                <p className="mt-1 text-[11px] text-slate-500">
                  {size(a.size)}
                </p>
                <div className="mt-3 flex flex-wrap justify-between gap-2">
                  <a
                    className="text-link"
                    href={api.imageUrl(a.id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Visualizar
                  </a>
                  <a
                    href={api.downloadUrl(a.id)}
                    className="text-link"
                    aria-label={`Baixar ${a.filename}`}
                  >
                    <Icon name="download" size={15} />
                  </a>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState icon="library" title="Nenhum arquivo nesta etapa">
          Os materiais reais aparecerão aqui conforme a produção avançar.
        </EmptyState>
      )}
    </section>
  );
}
