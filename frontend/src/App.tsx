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
import { Unavailable } from "./ui";

const nav = [
  { to: "/", label: "Visão Geral" },
  { to: "/linhas", label: "Linhas de Produção" },
  { to: "/execucoes", label: "Execuções" },
  { to: "/biblioteca", label: "Biblioteca" },
  { to: "/provedores", label: "Provedores" },
  { to: "/laboratorio", label: "Laboratório" },
  { to: "/configuracoes", label: "Configurações" },
];

export default function App() {
  return <AuthGate><Shell /></AuthGate>;
}

function Shell() {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen md:flex">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:hidden">
        <span className="font-semibold">ContentOS</span>
        <button aria-label="Menu" className="rounded border px-3 py-1 text-sm" onClick={() => setOpen(!open)}>Menu</button>
      </header>
      <aside className={`${open ? "block" : "hidden"} w-full shrink-0 border-r border-slate-200 bg-white md:block md:w-60`}>
        <div className="hidden px-5 py-5 text-lg font-semibold tracking-tight md:block">ContentOS</div>
        <nav className="flex flex-col gap-1 px-3 pb-4">
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} onClick={() => setOpen(false)}
              className={({ isActive }) => `rounded-lg px-3 py-2 text-sm ${isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <button className="mx-3 mb-4 rounded-lg px-3 py-2 text-left text-sm text-slate-500 hover:bg-slate-100" data-testid="logout"
          onClick={async () => { await api.logout(); window.dispatchEvent(new Event("unauthorized")); }}>Sair</button>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">
        <div className="mx-auto max-w-4xl">
          <Routes>
            <Route path="/" element={<Overview />} />
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
            <Route path="/configuracoes" element={<Unavailable title="Configurações" text="As configurações da plataforma ainda não estão disponíveis. Por ora, use o arquivo .env." />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
