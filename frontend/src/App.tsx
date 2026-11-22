import { useEffect, useState } from "react";
import { api } from "./api";
import { AuthGate } from "./components/AuthGate";
import {
  Link,
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { LineDetail } from "./pages/LineDetail";
import { LineForm } from "./pages/LineForm";
import { Lines } from "./pages/Lines";
import {
  ExperimentView,
  LabBenchmark,
  LabHistory,
  LabImages,
  LabLayout,
  LabText,
} from "./pages/Lab";
import {
  StudioLibrary,
  Productions,
  Publications,
} from "./pages/StudioCollections";
import { Icon } from "./components/StudioVisuals";
import { Overview } from "./pages/Overview";
import { ProviderDetail, ProviderForm, Providers } from "./pages/Providers";
import { RunDetail, Runs } from "./pages/Runs";
import { ApprovalDetailPage, Approvals, Settings } from "./approvals";
import {
  CreateFactory,
  FactoryInside,
  Factories,
  Home,
  Production,
} from "./studio";

const nav = [
  { to: "/", label: "Início", icon: "home" },
  { to: "/fabricas", label: "Minhas Fábricas", icon: "factory" },
  { to: "/producoes", label: "Produções", icon: "play" },
  { to: "/aprovacoes", label: "Aprovações", icon: "check" },
  { to: "/publicacoes", label: "Publicações", icon: "publish" },
  { to: "/biblioteca", label: "Biblioteca", icon: "library" },
];
const advanced = [
  { to: "/visao-geral", label: "Visão Geral" },
  { to: "/linhas", label: "Linhas de Produção" },
  { to: "/execucoes", label: "Execuções" },
  { to: "/provedores", label: "Provedores" },
];

export default function App() {
  return (
    <AuthGate>
      <Shell />
    </AuthGate>
  );
}

function Legacy({ children }: { children: React.ReactNode }) {
  return <div className="legacy-panel mx-auto max-w-5xl">{children}</div>;
}

function Shell() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);
  const section =
    nav.find((n) =>
      n.to === "/"
        ? location.pathname === "/"
        : location.pathname.startsWith(n.to),
    )?.label ??
    (location.pathname.includes("configuracoes")
      ? "Configurações"
      : "Espaço de criação");
  return (
    <div className="studio-shell lg:pl-60">
      {open && (
        <button
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          aria-label="Fechar menu"
          onClick={() => setOpen(false)}
        />
      )}
      <aside className={`sidebar ${open ? "flex" : "hidden lg:flex"}`}>
        <Link
          to="/"
          onClick={() => setOpen(false)}
          className="brand"
          aria-label="ContentOS Studio"
        >
          <span className="brand-mark">
            <Icon name="brand" size={30} />
          </span>
          <span>
            <span className="block text-lg font-semibold tracking-tight">
              Content<span className="text-cyan-300">OS</span>
            </span>
            <span className="block text-[9px] uppercase tracking-[.3em] text-slate-500">
              Estúdio criativo
            </span>
          </span>
        </Link>
        <Link
          to="/fabricas/nova"
          className="studio-primary mb-3 text-xs"
          onClick={() => setOpen(false)}
        >
          <Icon name="plus" size={16} />
          Criar Fábrica com IA
        </Link>
        <div className="min-h-0 flex-1 overflow-y-auto pb-4">
          <p className="nav-caption">Seu estúdio</p>
          <nav className="space-y-1" aria-label="Principal">
            {nav.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  `nav-link ${isActive ? "active" : ""}`
                }
              >
                <Icon name={n.icon} size={18} />
                {n.label}
              </NavLink>
            ))}
          </nav>
          <p className="nav-caption">Explorar</p>
          <NavLink
            to="/laboratorio"
            onClick={() => setOpen(false)}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <Icon name="lab" size={18} />
            Laboratório
          </NavLink>
          <details className="mt-2">
            <summary className="cursor-pointer px-3 py-3 text-xs text-slate-500">
              Ferramentas avançadas
            </summary>
            <nav aria-label="Avançado">
              {advanced.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  className="nav-link text-xs"
                  onClick={() => setOpen(false)}
                >
                  {n.label}
                </NavLink>
              ))}
            </nav>
          </details>
        </div>
        <div className="border-t border-white/[.07] py-4">
          <NavLink
            to="/configuracoes"
            onClick={() => setOpen(false)}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
          >
            <Icon name="settings" size={18} />
            Configurações
          </NavLink>
          <button
            className="nav-link w-full"
            data-testid="logout"
            onClick={async () => {
              await api.logout();
              window.dispatchEvent(new Event("unauthorized"));
            }}
          >
            <Icon name="logout" size={18} />
            Sair do estúdio
          </button>
        </div>
      </aside>
      <header className="topbar">
        <div className="flex items-center gap-3">
          <button
            aria-label={open ? "Fechar menu" : "Abrir menu"}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
            className="rounded p-2 text-slate-300 lg:hidden"
          >
            <Icon name="menu" />
          </button>
          <span className="hidden text-xs text-slate-500 sm:inline">
            Estúdio <span className="mx-3 text-slate-600">/</span>
          </span>
          <span className="text-xs font-medium text-slate-300">{section}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-[11px] text-slate-500 sm:block">
            Seu espaço criativo
          </span>
          <span className="flex h-8 w-8 items-center justify-center rounded-full border border-cyan-300/20 bg-cyan-300/10 text-[10px] font-semibold text-cyan-200">
            OS
          </span>
        </div>
      </header>
      <main
        className={`workspace ${location.pathname === "/" ? "workspace-home" : ""}`}
      >
        <div className="mx-auto max-w-[1440px]">
          <Routes key={location.pathname}>
            <Route path="/" element={<Home />} />
            <Route path="/fabricas" element={<Factories />} />
            <Route path="/fabricas/nova" element={<CreateFactory />} />
            <Route path="/fabricas/:id" element={<FactoryInside />} />
            <Route path="/producoes" element={<Productions />} />
            <Route path="/producao/:id" element={<Production />} />
            <Route path="/aprovacoes" element={<Approvals />} />
            <Route path="/aprovacoes/:id" element={<ApprovalDetailPage />} />
            <Route path="/publicacoes" element={<Publications />} />
            <Route path="/biblioteca" element={<StudioLibrary />} />
            <Route path="/configuracoes" element={<Settings />} />
            <Route
              path="/*"
              element={
                <Legacy>
                  <LegacyRoutes />
                </Legacy>
              }
            />
          </Routes>
        </div>
      </main>
    </div>
  );
}

function LegacyRoutes() {
  return (
    <Routes>
      <Route path="/visao-geral" element={<Overview />} />
      <Route path="/linhas" element={<Lines />} />
      <Route path="/linhas/nova" element={<LineForm />} />
      <Route path="/linhas/:id" element={<LineDetail />} />
      <Route path="/linhas/:id/editar" element={<LineForm />} />
      <Route path="/execucoes" element={<Runs />} />
      <Route path="/execucoes/:id" element={<RunDetail />} />
      <Route path="/provedores" element={<Providers />} />
      <Route path="/provedores/novo" element={<ProviderForm />} />
      <Route path="/provedores/:id" element={<ProviderDetail />} />
      <Route path="/provedores/:id/editar" element={<ProviderForm />} />
      <Route path="/laboratorio" element={<LabLayout />}>
        <Route index element={<Navigate to="imagens" replace />} />
        <Route path="imagens" element={<LabImages />} />
        <Route path="texto" element={<LabText />} />
        <Route path="benchmark" element={<LabBenchmark />} />
        <Route path="experimentos" element={<LabHistory />} />
        <Route path="experimentos/:id" element={<ExperimentView />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
