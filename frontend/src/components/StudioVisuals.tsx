import { CSSProperties, ReactNode } from "react";
import { Line } from "../api";

const paths: Record<string, ReactNode> = {
  mic: <><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8" /></>,
  list: <path d="M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1" />,
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M7 2v6m10-6v6M3 11h18M7 15h2m4 0h2m-8 3h2" />
    </>
  ),
  "chevron-left": <path d="m14 5-7 7 7 7" />,
  "chevron-right": <path d="m10 5 7 7-7 7" />,
  download: <path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4" />,
  eye: (
    <>
      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  home: (
    <>
      <path d="m3 10 9-7 9 7v10H4V10" />
      <path d="M9 21v-8h6v8" />
    </>
  ),
  factory: (
    <>
      <path d="m12 3 10 5-10 5L2 8l10-5Z" />
      <path d="m2 12 10 5 10-5M2 16l10 5 10-5" />
    </>
  ),
  brand: (
    <>
      <path d="M5 3 21 12 5 21V3Z" strokeWidth="3" />
      <path d="m5 3 6 3.5M5 21l6-3.5" stroke="#19c4d8" strokeWidth="3" />
    </>
  ),
  audio: (
    <>
      <path d="M4 10v4m4-8v12m4-16v20m4-16v12m4-8v4" />
    </>
  ),

  spark: (
    <>
      <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z" />
      <path d="m20 2 .5 1.5L22 4l-1.5.5L20 6l-.5-1.5L18 4l1.5-.5Z" />
    </>
  ),
  play: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <path d="m10 8 6 4-6 4V8Z" />
    </>
  ),
  check: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12 3 3 5-6" />
    </>
  ),
  publish: (
    <>
      <path d="M4 15v5h16v-5M12 16V3m-5 5 5-5 5 5" />
    </>
  ),
  library: (
    <>
      <rect x="3" y="7" width="18" height="14" rx="2" />
      <path d="M7 7V3h10v4m-9 6 3 3 3-4 4 5H6" />
    </>
  ),
  settings: (
    <>
      <path d="m9 3-1 3-3 1 1 3-2 2 2 2-1 3 3 1 1 3h6l1-3 3-1-1-3 2-2-2-2 1-3-3-1-1-3H9Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  search: (
    <>
      <circle cx="10" cy="10" r="6" />
      <path d="m15 15 6 6" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  logout: (
    <>
      <path d="M10 4H4v16h6m-1-8h12m-5-5 5 5-5 5" />
    </>
  ),
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  lab: (
    <>
      <path d="M9 3h6m-5 0v6L4 19q-1 2 2 2h12q3 0 2-2L14 9V3M7 15h10" />
    </>
  ),
  file: (
    <>
      <path d="M5 3h9l5 5v13H5V3Zm9 0v6h5M8 14h8M8 17h5" />
    </>
  ),
};
export function Icon({
  name,
  size = 20,
  className = "",
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`shrink-0 ${className}`}
    >
      {paths[name] ?? paths.factory}
    </svg>
  );
}
export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div className="flex min-w-0 items-start gap-4">
        <span className="page-title-icon">
          <Icon
            name={
              (
                {
                  "Minhas Fábricas": "factory",
                  Produções: "play",
                  Aprovações: "check",
                  Publicações: "publish",
                  Biblioteca: "library",
                  "Criar Fábrica com IA": "spark",
                  Configurações: "settings",
                } as Record<string, string>
              )[title] ?? "factory"
            }
            size={32}
          />
        </span>
        <div>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h1>{title}</h1>
          {description && (
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-400">
              {description}
            </p>
          )}
        </div>
      </div>
      {action}
    </div>
  );
}
export function EmptyState({
  icon = "factory",
  title,
  children,
  action,
}: {
  icon?: string;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon name={icon} size={26} />
      </span>
      <h3>{title}</h3>
      <div className="max-w-md text-sm leading-relaxed text-slate-400">
        {children}
      </div>
      {action}
    </div>
  );
}
export function LoadingCards({ count = 3 }: { count?: number }) {
  return (
    <div
      className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3"
      role="status"
      aria-label="Carregando"
    >
      <span className="sr-only">Carregando…</span>
      {Array.from({ length: count }, (_, i) => (
        <div className="skeleton-card" key={i}>
          <div className="aspect-video bg-white/5" />
          <div className="m-5 h-4 w-2/3 rounded bg-white/5" />
          <div className="m-5 h-3 w-1/2 rounded bg-white/5" />
        </div>
      ))}
    </div>
  );
}
export const dateLabel = (date: string) =>
  new Date(date).toLocaleDateString("pt-BR", {
    day: "numeric",
    month: "short",
  });
export function factoryTheme(f: Pick<Line, "name" | "description" | "config">) {
  const text =
    `${f.name} ${f.description} ${f.config.theme ?? ""} ${f.config.visual_style ?? ""}`.toLowerCase();
  if (
    /terror|horror|sombr|myst|mist[eé]r|abandon|assombr/.test(text) &&
    !/univers|cosmo|astrono/.test(text)
  )
    return "nocturne";
  if (/univers|cosmo|astrono|espa[cç]|planet|gal[aá]x|space/.test(text))
    return "cosmos";
  if (/nature|natur|florest|animal|ambien|ocean/.test(text)) return "nature";
  if (/hist[oó]r|ancient|civiliza|mediev/.test(text)) return "history";
  if (/educa|ci[eê]n|science|aprend|tech|tecnol/.test(text)) return "science";
  return "abstract";
}
/** Capas editoriais locais. Não representam arquivos produzidos. */
export function FactoryCover({
  factory,
  image,
  className = "",
}: {
  factory: Pick<Line, "name" | "description" | "config">;
  image?: string;
  className?: string;
}) {
  const theme = factoryTheme(factory);
  const seed = [...factory.name].reduce((n, c) => n + c.charCodeAt(0), 0);
  return (
    <div
      className={`factory-cover cover-${theme} ${className}`}
      style={{ "--seed": `${seed % 35}deg` } as CSSProperties}
    >
      {image ? (
        <img src={image} alt="" loading="lazy" />
      ) : (
        <svg
          viewBox="0 0 800 450"
          fill="none"
          aria-hidden="true"
          preserveAspectRatio="xMidYMid slice"
        >
          {theme === "cosmos" ? (
            <>
              <g fill="#b6dee4">
                {Array.from({ length: 65 }, (_, i) => (
                  <circle
                    key={i}
                    cx={(i * 137 + seed) % 800}
                    cy={(i * 97) % 450}
                    r={i % 5 === 0 ? 1.5 : 0.7}
                    opacity={0.2 + (i % 4) * 0.2}
                  />
                ))}
              </g>
              <circle cx="530" cy="220" r="125" fill="#143946" />
              <path
                d="M419 162a125 125 0 0 1 210 130 125 125 0 0 0-210-130Z"
                fill="#4c8d97"
              />
              <ellipse
                cx="530"
                cy="230"
                rx="240"
                ry="40"
                transform="rotate(-28 530 230)"
                stroke="#6badae"
                strokeWidth="3"
              />
              <ellipse
                cx="530"
                cy="230"
                rx="232"
                ry="34"
                transform="rotate(-28 530 230)"
                stroke="#6badae"
                strokeWidth="10"
                opacity=".15"
              />
              <circle cx="183" cy="109" r="23" fill="#8fa9a9" opacity=".6" />
            </>
          ) : theme === "nocturne" ? (
            <>
              <circle cx="565" cy="110" r="65" fill="#bab6a0" opacity=".65" />
              <path d="M0 350 250 295 800 350V450H0Z" fill="#0a141a" />
              <path d="M310 340V190l110-85 115 85v150" fill="#101b20" />
              <path
                d="m285 195 135-110 143 110"
                stroke="#26343a"
                strokeWidth="9"
              />
              <path d="M398 340v-83h45v83" fill="#050b0d" />
              <path
                d="M349 202h28v40h-28zm119 0h28v40h-28z"
                fill="#c79455"
                opacity=".8"
              />
              {[50, 140, 650, 740].map((x) => (
                <g key={x} stroke="#091318" strokeWidth="14">
                  <path
                    d={`M${x} 450V100m0 95-45-55m45 110 52-66m-52-30 35-55`}
                  />
                </g>
              ))}
            </>
          ) : theme === "nature" ? (
            <>
              <circle cx="550" cy="105" r="53" fill="#d2c293" opacity=".6" />
              <path
                d="m0 345 175-205 175 180L510 100 800 350v100H0Z"
                fill="#2c5755"
              />
              <path
                d="m0 390 200-150 195 130 230-158 175 150v88H0Z"
                fill="#173e3b"
              />
              <path d="m0 400 260-75 230 68 310-86v143H0" fill="#0a292b" />
              <path
                d="M430 320q-140 55 30 130h100q-210-90-130-130"
                fill="#89bab0"
                opacity=".4"
              />
            </>
          ) : theme === "history" ? (
            <>
              <circle cx="580" cy="105" r="90" fill="#b89563" opacity=".25" />
              <path d="M0 385 230 320l320 30 250-65v165H0Z" fill="#665b45" />
              <path d="m250 190 155-85 155 85H250" fill="#a28a64" />
              {[280, 350, 420, 490].map((x) => (
                <g key={x} fill="#907e60">
                  <path d={`M${x} 200h35v160h-35z`} />
                  <path d={`M${x - 6} 195h47v15h-47zm0 155h47v15h-47z`} />
                </g>
              ))}
              <path d="M242 370h330v20H242" fill="#a28a64" />
            </>
          ) : theme === "science" ? (
            <>
              <g stroke="#39777e" opacity=".25">
                {Array.from({ length: 16 }, (_, i) => (
                  <path key={i} d={`M${i * 60} 0v450M0 ${i * 60}h800`} />
                ))}
              </g>
              <g
                stroke="#66c6c5"
                strokeWidth="2"
                transform="translate(485 220)"
              >
                <ellipse rx="160" ry="58" />
                <ellipse rx="160" ry="58" transform="rotate(60)" />
                <ellipse rx="160" ry="58" transform="rotate(-60)" />
                <circle r="22" fill="#46a5ae" />
              </g>
              <circle cx="645" cy="220" r="8" fill="#c6e6d9" />
            </>
          ) : (
            <>
              <g
                transform={`translate(490 235) rotate(${seed % 35})`}
                stroke="#5aa7ae"
              >
                {Array.from({ length: 9 }, (_, i) => (
                  <rect
                    key={i}
                    x={-125 + i * 8}
                    y={-125 + i * 8}
                    width={250 - i * 16}
                    height={250 - i * 16}
                    rx="32"
                    transform={`rotate(${i * 7})`}
                    opacity={0.18 + i * 0.07}
                  />
                ))}
              </g>
              <circle cx="210" cy="135" r="45" stroke="#76aca9" opacity=".3" />
            </>
          )}
        </svg>
      )}
      <div className="cover-shade" />
    </div>
  );
}
