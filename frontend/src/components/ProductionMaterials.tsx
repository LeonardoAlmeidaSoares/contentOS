import { Link } from "react-router-dom";
import { api, Run } from "../api";
import { isActiveRun } from "../ui";
import { Icon } from "./StudioVisuals";

const labels: Record<string, string> = {
  script: "Roteiro",
  scenes: "Cenas",
  images: "Imagens",
  narration: "Narração",
  subtitles: "Legendas",
  render: "Montagem",
  export: "Exportação",
};

/** Estados e materiais da execução real; nenhum percentual interno é estimado. */
export function ProductionWorkspace({ run }: { run: Run }) {
  const done = run.steps.filter((s) => s.status === "succeeded").length;
  const current = run.steps.find((s) =>
    ["running", "retrying"].includes(s.status),
  );
  const title = run.steps
    .map((s) => s.output?.title)
    .find((v) => typeof v === "string") as string | undefined;
  const images = run.artifacts.filter(
    (a) =>
      a.content_type.startsWith("image/") && a.filename !== "miniatura.jpg",
  );
  const audio = run.artifacts.find((a) => a.content_type.startsWith("audio/"));
  const video = run.artifacts.find((a) => a.filename === "video.mp4");
  const poster = run.artifacts.find((a) => a.filename === "miniatura.jpg");
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
      [s.heading, s.text, ...(s.scenes ?? []).map((v) => v.narration)]
        .filter(Boolean)
        .join("\n\n"),
    )
    .join("\n\n");
  return (
    <section
      className="studio-card production-workspace p-5"
      aria-label="Produção e materiais"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="rounded-xl bg-cyan-300/10 p-3 text-cyan-300">
            <Icon name="play" size={25} />
          </span>
          <div>
            <p className="mb-1 text-xs font-medium text-cyan-200">
              {isActiveRun(run.status)
                ? "Produção em andamento"
                : "Última produção"}
            </p>
            <h2 className="text-lg font-semibold">
              {title ?? run.line_name ?? "Produção"}
            </h2>
          </div>
        </div>
        <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1.5 text-xs text-cyan-100">
          {done} de {run.steps.length} etapas concluídas
        </span>
      </div>
      <ol className="production-track" aria-label="Etapas da produção">
        {run.steps.map((s) => (
          <li
            key={s.position}
            className={
              s.status === "succeeded"
                ? "done"
                : s.status === "failed"
                  ? "failed"
                  : ["running", "retrying"].includes(s.status)
                    ? "current"
                    : ""
            }
          >
            <span>
              {s.status === "succeeded" ? (
                <Icon name="check" size={19} />
              ) : s.status === "failed" ? (
                "!"
              ) : (
                s.position
              )}
            </span>
            <p>{labels[s.name] ?? s.name}</p>
          </li>
        ))}
      </ol>
      {current?.message && (
        <p className="mb-4 text-xs text-slate-400">{current.message}</p>
      )}
      {video && (
        <div className="mb-5 overflow-hidden rounded-xl border border-white/10">
          <video
            controls
            preload="metadata"
            src={api.imageUrl(video.id)}
            poster={poster ? api.imageUrl(poster.id) : undefined}
            className="aspect-video w-full bg-black"
            aria-label={title ?? "Prévia da produção"}
          />
        </div>
      )}
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Icon name="library" size={17} className="text-cyan-300" />
        Materiais do conteúdo
      </h3>
      <div className="materials-grid">
        <article>
          <h4>
            <Icon name="file" size={18} />
            Roteiro
          </h4>
          {script ? (
            <details>
              <summary className="studio-ghost mt-3 cursor-pointer py-2 text-xs">
                Ver roteiro
              </summary>
              <p className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-slate-300">
                {script}
              </p>
            </details>
          ) : (
            <p className="material-pending">Ainda não disponível</p>
          )}
        </article>
        <article>
          <h4>
            <Icon name="library" size={18} />
            Imagens{" "}
            <span className="ml-auto text-xs text-slate-400">
              {images.length}
            </span>
          </h4>
          {images.length ? (
            <div className="mt-3 grid grid-cols-3 gap-1">
              {images.slice(0, 3).map((a) => (
                <a
                  href={api.imageUrl(a.id)}
                  target="_blank"
                  rel="noreferrer"
                  key={a.id}
                  title={a.filename}
                >
                  <img
                    src={api.imageUrl(a.id)}
                    alt={a.filename}
                    className="aspect-square w-full rounded object-cover"
                  />
                </a>
              ))}
            </div>
          ) : (
            <p className="material-pending">Ainda não disponíveis</p>
          )}
        </article>
        <article>
          <h4>
            <Icon name="audio" size={18} />
            Narração
          </h4>
          {audio ? (
            <>
              <p
                className="my-3 truncate text-xs text-slate-400"
                title={audio.filename}
              >
                {audio.filename}
              </p>
              <audio
                src={api.imageUrl(audio.id)}
                controls
                preload="metadata"
                className="w-full"
                aria-label={`Ouvir ${audio.filename}`}
              />
            </>
          ) : (
            <p className="material-pending">Ainda não disponível</p>
          )}
        </article>
      </div>
      <Link to={`/producao/${run.id}`} className="text-link mt-5">
        Abrir produção e todos os arquivos <Icon name="arrow" size={15} />
      </Link>
    </section>
  );
}
