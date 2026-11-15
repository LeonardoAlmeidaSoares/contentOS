import { FormEvent, ReactNode, useEffect, useState } from "react";
import { api } from "../api";
import { btnPrimary } from "../ui";

export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"loading" | "in" | "out">("loading");
  const [token, setToken] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.me().then(() => setState("in")).catch(() => setState("out"));
    const h = () => setState("out");
    window.addEventListener("unauthorized", h);
    return () => window.removeEventListener("unauthorized", h);
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try { await api.login(token); setToken(""); setState("in"); } catch (x) { setErr((x as Error).message); }
  };

  if (state === "loading") return <p className="p-8 text-sm text-slate-500">Carregando…</p>;
  if (state === "in") return <>{children}</>;
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-lg font-semibold">ContentOS</h1>
        <p className="text-sm text-slate-500">Acesso administrativo. Informe o token configurado em <code>ADMIN_TOKEN</code>.</p>
        <input type="password" autoFocus value={token} onChange={(e) => setToken(e.target.value)} data-testid="login-token"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="Token de administrador" />
        {err && <p className="text-sm text-red-600" data-testid="login-error">{err}</p>}
        <button className={`${btnPrimary} w-full`} data-testid="login-submit">Entrar</button>
      </form>
    </div>
  );
}
