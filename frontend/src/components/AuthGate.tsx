import { FormEvent, ReactNode, useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "./StudioVisuals";

export function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"loading" | "in" | "out">("loading");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .me()
      .then(() => setState("in"))
      .catch(() => setState("out"));
    const h = () => setState("out");
    window.addEventListener("unauthorized", h);
    return () => window.removeEventListener("unauthorized", h);
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await api.login(token);
      setToken("");
      setState("in");
    } catch (x) {
      setErr((x as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (state === "loading")
    return <p className="p-8 text-sm text-slate-500">Carregando…</p>;
  if (state === "in") return <>{children}</>;
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form
        onSubmit={submit}
        className="studio-card w-full max-w-md space-y-5 p-8"
      >
        <span className="brand-mark">
          <Icon name="play" size={26} />
        </span>
        <div>
          <p className="eyebrow mt-6">ContentOS Studio</p>
          <h1 className="text-2xl font-semibold">
            Seu próximo projeto começa aqui.
          </h1>
        </div>
        <p className="text-sm text-slate-500">
          Entre com seu token de acesso para abrir o estúdio.
        </p>
        <input
          type="password"
          autoFocus
          value={token}
          onChange={(e) => setToken(e.target.value)}
          data-testid="login-token"
          className="studio-input"
          aria-label="Token de acesso"
          placeholder="Token de acesso"
        />
        {err && (
          <p className="text-sm text-red-300" data-testid="login-error">
            {err}
          </p>
        )}
        <button
          className="studio-primary w-full"
          disabled={busy || !token.trim()}
          data-testid="login-submit"
        >
          {busy ? "Entrando…" : "Entrar no estúdio"}
        </button>
      </form>
    </div>
  );
}
