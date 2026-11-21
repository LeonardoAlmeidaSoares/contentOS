import { useState } from "react";
import { api } from "./api";
import { AuthGate } from "./components/AuthGate";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { LineDetail } from "./pages/LineDetail";
import { LineForm } from "./pages/LineForm";
import { Lines } from "./pages/Lines";
import { ExperimentView, LabBenchmark, LabHistory, LabImages, LabLayout, LabText } from "./pages/Lab";
import { Library } from "./pages/Library";
import { Overview } from "./pages/Overview";
import { ProviderDetail, ProviderForm, Providers } from "./pages/Providers";
import { RunDetail, Runs } from "./pages/Runs";
import { ApprovalDetailPage, Approvals, Settings } from "./approvals";
import { CreateFactory, FactoryInside, Factories, Home, Production } from "./studio";

const nav = [
  { to: "/", label: "Início", icon: "🏠" },
  { to: "/fabricas", label: "Minhas Fábricas", icon: "🏭" },
  { to: "/fabricas/nova", label: "Criar Fábrica com IA", icon: "✨" },
  { to: "/aprovacoes", label: "Aprovações", icon: "✅" },
  { to: "/configuracoes", label: "Configurações", icon: "⚙️" },
];
const advanced = [
  { to: "/visao-geral", label: "Visão Geral" },
  { to: "/linhas", label: "Linhas de Produção" },
  { to: "/execucoes", label: "Execuções" },
  { to: "/biblioteca", label: "Biblioteca" },
  { to: "/provedores", label: "Provedores" },
  { to: "/laboratorio", label: "Laboratório" },
];

export default function App() {
  return <AuthGate><Shell /></AuthGate>;
}

const link = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition ${isActive ? "bg-cyan-400/15 text-cyan-300" : "text-slate-300 hover:bg-petrol-800"}`;

/** Telas técnicas anteriores (tema claro) ficam em um painel próprio dentro do Studio. */
function Legacy({ children }: { children: React.ReactNode }) {
  return <div className="rounded-2xl bg-slate-50 p-5 text-slate-900 md:p-8"><div className="mx-auto max-w-4xl">{children}</div></div>;
}

function Shell() {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen md:flex">
      <header className="flex items-center justify-between border-b border-petrol-800 bg-petrol-900 px-4 py-3 md:hidden">
        <span className="font-semibold text-cyan-300">ContentOS Studio</span>
        <button aria-label="Menu" className="rounded-lg border border-petrol-600 px-3 py-1 text-sm" onClick={() => setOpen(!open)}>Menu</button>
      </header>
      <aside className={`${open ? "block" : "hidden"} w-full shrink-0 border-r border-petrol-800 bg-petrol-900 md:block md:w-64`}>
        <div className="hidden px-5 py-6 md:block"><div className="text-lg font-semibold tracking-tight text-cyan-300">ContentOS</div><div className="text-xs text-slate-500">Studio</div></div>
        <nav className="flex flex-col gap-1 px-3 pb-4">
          {nav.map((n) => <NavLink key={n.to} to={n.to} end onClick={() => setOpen(false)} className={link}><span>{n.icon}</span>{n.label}</NavLink>)}
          <div className="px-3 pb-1 pt-5 text-xs uppercase tracking-wider text-slate-500">Avançado</div>
          {advanced.map((n) => <NavLink key={n.to} to={n.to} onClick={() => setOpen(false)} className={link}>{n.label}</NavLink>)}
        </nav>
        <button className="mx-3 mb-4 rounded-xl px-3 py-2 text-left text-sm text-slate-500 hover:bg-petrol-800" data-testid="logout"
          onClick={async () => { await api.logout(); window.dispatchEvent(new Event("unauthorized")); }}>Sair</button>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">
        <div className="mx-auto max-w-6xl">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/fabricas" element={<Factories />} />
            <Route path="/fabricas/nova" element={<CreateFactory />} />
            <Route path="/fabricas/:id" element={<FactoryInside />} />
            <Route path="/producao/:id" element={<Production />} />
            <Route path="/aprovacoes" element={<Approvals />} />
            <Route path="/aprovacoes/:id" element={<ApprovalDetailPage />} />
            <Route path="/configuracoes" element={<Settings />} />
            <Route path="/*" element={<Legacy><LegacyRoutes /></Legacy>} />
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
      <Route path="/biblioteca" element={<Library />} />
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
    </Routes>
  );
}
