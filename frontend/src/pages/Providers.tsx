import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Provider, Service, api } from "../api";
import { usePoll } from "../hooks";
import { Badge, Card, btn, btnPrimary, fmt, money } from "../ui";

const field = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm";

export function Providers() {
  const { data: list, error } = usePoll(api.providers, [], 4000);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Provedores</h1>
        <Link to="/provedores/novo" className={btnPrimary} data-testid="new-provider">Novo provedor</Link>
      </div>
      {error && <p className="text-sm text-red-600">Falha ao carregar provedores.</p>}
      <div className="grid gap-4">
        {list?.map((p) => (
          <Link key={p.id} to={`/provedores/${p.id}`} data-testid="provider-card" className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm hover:border-slate-400">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2"><span className="font-medium">{p.name}</span><Badge status={p.active ? "active" : "inactive"} /></div>
              <Badge status={p.status} />
            </div>
            <p className="mt-1 text-xs text-slate-500">{p.service_label} · {p.capabilities.map((c) => (c === "image" ? "imagem" : "texto")).join(", ") || "sem modelos"} · {p.models.length} modelos</p>
            <p className="mt-2 text-xs text-slate-600">Consumo no mês: {money(p.month_cost)} / limite {money(p.limit_month_usd)}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function ProviderForm() {
  const { id } = useParams();
  const nav = useNavigate();
  const [services, setServices] = useState<Service[]>([]);
  const [prov, setProv] = useState<Provider | null>(null);
  const [f, setF] = useState({ service: "", name: "", base_url: "", api_key: "", limit: "", config: "{}", models: "[]", clear: false });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((p) => ({ ...p, [k]: e.target.value }));
  const svc = services.find((s) => s.service === f.service);

  useEffect(() => {
    api.services().then(setServices);
    if (id) api.provider(id).then((p) => {
      setProv(p);
      setF({ service: p.service, name: p.name, base_url: p.base_url ?? "", api_key: "", limit: p.limit_month_usd?.toString() ?? "",
        config: JSON.stringify(p.config, null, 2), models: JSON.stringify(p.models, null, 2), clear: false });
    });
  }, [id]);

  const pick = (service: string) => {
    const s = services.find((x) => x.service === service);
    setF((p) => ({ ...p, service, name: p.name || s?.label || "", base_url: s?.default_base_url ?? "", models: JSON.stringify(s?.known_models ?? [], null, 2) }));
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    let config, models;
    try { config = JSON.parse(f.config); models = JSON.parse(f.models); } catch { return setErr("Configurações e modelos devem ser JSON válido."); }
    const body = { name: f.name, base_url: f.base_url || null, config, models, limit_month_usd: f.limit === "" ? null : Number(f.limit) };
    try {
      const saved = id
        ? await api.updateProvider(id, { ...body, ...(f.api_key ? { api_key: f.api_key } : {}), clear_credentials: f.clear })
        : await api.createProvider({ ...body, service: f.service, api_key: f.api_key || undefined });
      nav(`/provedores/${saved.id}`);
    } catch (x) { setErr((x as Error).message); }
  };

  return (
    <form onSubmit={submit} className="space-y-6">
      <div>
        <Link to={id ? `/provedores/${id}` : "/provedores"} className="text-sm text-blue-600 hover:underline">← Voltar</Link>
        <h1 className="mt-2 text-2xl font-semibold">{id ? `Editar ${prov?.name ?? ""}` : "Novo provedor"}</h1>
      </div>
      <Card title="Identificação">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm">Serviço
            <select className={field} value={f.service} disabled={!!id} onChange={(e) => pick(e.target.value)} data-testid="p-service">
              <option value="">Selecione…</option>
              {services.map((s) => <option key={s.service} value={s.service}>{s.label}</option>)}
            </select></label>
          <label className="text-sm">Nome<input required className={field} value={f.name} onChange={set("name")} data-testid="p-name" /></label>
          <label className="text-sm">URL da API<input className={field} value={f.base_url} onChange={set("base_url")} placeholder={svc?.default_base_url ?? ""} /></label>
          <label className="text-sm">Limite mensal (US$)<input type="number" step="any" min={0} className={field} value={f.limit} onChange={set("limit")} /></label>
        </div>
      </Card>
      {(!svc || svc.needs_key) && (
        <Card title="Credencial">
          <label className="text-sm">Chave de API
            <input type="password" autoComplete="new-password" className={field} value={f.api_key} onChange={set("api_key")} data-testid="p-key"
              placeholder={prov?.has_credentials ? `mantida (${prov.credentials_hint})` : "cole a chave"} /></label>
          <p className="mt-2 text-xs text-slate-500">Armazenada criptografada; nunca é exibida de volta nem aparece em logs.</p>
          {id && prov?.has_credentials && <label className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={f.clear} onChange={(e) => setF({ ...f, clear: e.target.checked })} />Remover credencial (desativa o provedor)</label>}
        </Card>
      )}
      <Card title="Modelos, capacidades e preços (JSON)">
        {svc && <p className="mb-2 text-xs text-slate-500">Preços semeados: {svc.pricing_source}. Confira e ajuste conforme sua conta; modelo sem preço exige autorização explícita para executar.</p>}
        <textarea className={`${field} h-64 font-mono text-xs`} value={f.models} onChange={set("models")} data-testid="p-models" />
      </Card>
      <Card title="Configurações específicas (JSON)"><textarea className={`${field} h-20 font-mono text-xs`} value={f.config} onChange={set("config")} />
        <p className="mt-1 text-xs text-slate-500">Não coloque segredos aqui.</p></Card>
      {err && <p className="text-sm text-red-600" data-testid="form-error">{err}</p>}
      <div className="flex gap-3"><button className={btnPrimary} data-testid="save-provider">Salvar</button><Link className={btn} to={id ? `/provedores/${id}` : "/provedores"}>Cancelar</Link></div>
    </form>
  );
}

export function ProviderDetail() {
  const { id = "" } = useParams();
  const [tick, setTick] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: p, error } = usePoll(() => api.provider(id), [id, tick], 4000);
  const { data: u } = usePoll(() => api.usage(id), [id, tick], 4000);
  const act = async (a: "activate" | "deactivate" | "test") => {
    setMsg(null); setBusy(true);
    try { await api.providerAction(id, a); setTick((t) => t + 1); } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  if (error && !p) return <p className="text-sm text-red-600">Provedor não encontrado.</p>;
  if (!p) return <p className="text-sm text-slate-500">Carregando…</p>;
  return (
    <div className="space-y-6">
      <div>
        <Link to="/provedores" className="text-sm text-blue-600 hover:underline">← Provedores</Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3"><h1 className="text-2xl font-semibold" data-testid="provider-title">{p.name}</h1><Badge status={p.active ? "active" : "inactive"} /><Badge status={p.status} /></div>
          <div className="flex flex-wrap gap-2">
            <button className={btn} disabled={busy} onClick={() => act("test")} data-testid="test-provider">Testar conexão</button>
            <button className={btn} onClick={() => act(p.active ? "deactivate" : "activate")} data-testid="toggle-provider">{p.active ? "Desativar" : "Ativar"}</button>
            <Link className={btn} to={`/provedores/${id}/editar`}>Editar</Link>
          </div>
        </div>
        <p className="mt-1 text-xs text-slate-500">{p.service_label} · {p.base_url ?? "—"} · credencial: {p.has_credentials ? p.credentials_hint : "não cadastrada"}</p>
        {p.status_message && <p className={`mt-2 text-sm ${p.status === "error" ? "text-red-600" : "text-slate-600"}`} data-testid="status-message">{p.status_message} <span className="text-xs text-slate-400">({fmt(p.status_checked_at)})</span></p>}
        {msg && <p className="mt-2 text-sm text-red-600" data-testid="action-error">{msg}</p>}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[["Consumo no mês", `${money(u?.month.spent ?? p.month_cost)} / ${money(p.limit_month_usd)}`],
          ["Estimado × efetivo (conciliado)", u ? `${money(u.month.reconciled_estimated)} × ${money(u.month.reconciled_actual)}` : "—"],
          ["Falhas no mês", String(u?.month.failures ?? 0)], ["Modelos", String(p.models.length)]].map(([k, v]) => (
          <div key={k} className="rounded-xl border border-slate-200 bg-white p-4 text-sm"><div className="text-xs text-slate-400">{k}</div><div className="mt-1 font-medium">{v}</div></div>
        ))}
      </div>
      <Card title="Modelos e preços">
        <div className="overflow-x-auto"><table className="w-full text-left text-xs">
          <thead className="text-slate-400"><tr><th className="py-1 pr-3">Modelo</th><th className="pr-3">Capacidades</th><th className="pr-3">Ativo</th><th>Preço (configurado)</th></tr></thead>
          <tbody>{p.models.map((m) => (
            <tr key={m.id} className="border-t border-slate-100 align-top"><td className="py-2 pr-3 font-mono">{m.id}</td><td className="pr-3">{m.capabilities.join(", ")}</td>
              <td className="pr-3">{m.active === false ? "não" : "sim"}</td>
              <td className="max-w-md break-words text-slate-500">{m.pricing && Object.keys(m.pricing).length ? JSON.stringify(m.pricing) : "não configurado (exige autorização)"}</td></tr>))}</tbody>
        </table></div>
      </Card>
      <Card title="Histórico de utilização e falhas">
        {u && u.items.length === 0 && <p className="text-sm text-slate-500">Sem utilização registrada.</p>}
        <div className="overflow-x-auto"><table className="w-full text-left text-xs">
          <thead className="text-slate-400"><tr><th className="py-1 pr-3">Quando</th><th className="pr-3">Modelo</th><th className="pr-3">Status</th><th className="pr-3">Estim.</th><th className="pr-3">Efetivo</th><th className="pr-3">Tempo</th><th>Erro</th></tr></thead>
          <tbody>{u?.items.map((x) => (
            <tr key={x.id} className="border-t border-slate-100 align-top" data-testid="usage-row"><td className="py-2 pr-3">{fmt(x.created_at)}</td><td className="pr-3 font-mono">{x.model}</td>
              <td className="pr-3"><Badge status={x.status === "succeeded" ? "succeeded" : x.status === "reserved" ? "running" : x.status === "failed" ? "failed" : x.status} /></td>
              <td className="pr-3">{money(x.cost_estimated)}</td><td className="pr-3">{money(x.cost_effective)} <span className="text-slate-400">{x.cost_source}{x.cost_unknown ? "*" : ""}</span></td>
              <td className="pr-3">{x.duration_ms ? `${(x.duration_ms / 1000).toFixed(1)}s` : "—"}</td><td className="max-w-xs break-words text-red-600">{x.error}</td></tr>))}</tbody>
        </table></div>
        <p className="mt-2 text-xs text-slate-400">* executada com autorização explícita de custo desconhecido.</p>
      </Card>
    </div>
  );
}
