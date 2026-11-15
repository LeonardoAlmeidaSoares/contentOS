import { ModelCfg, Provider, Target } from "../api";

export const same = (a: Target, b: Target) => a.provider_id === b.provider_id && a.model === b.model;

export function TargetPicker({ kind, providers, value, onChange }: {
  kind: "image" | "text"; providers: Provider[]; value: Target[]; onChange: (t: Target[]) => void;
}) {
  const active = providers.filter((p) => p.active && p.models.some((m) => m.capabilities.includes(kind) && m.active !== false));
  if (active.length === 0)
    return <p className="text-sm text-amber-700">Nenhum provedor ativo com suporte a {kind === "image" ? "imagens" : "texto"}. Ative um em Provedores.</p>;
  const toggle = (t: Target) => onChange(value.some((v) => same(v, t)) ? value.filter((v) => !same(v, t)) : [...value, t]);
  return (
    <div className="space-y-3">
      {active.map((p) => (
        <div key={p.id}>
          <div className="text-xs font-medium text-slate-500">{p.name}</div>
          <div className="mt-1 flex flex-wrap gap-2">
            {p.models.filter((m: ModelCfg) => m.capabilities.includes(kind) && m.active !== false).map((m) => {
              const t = { provider_id: p.id, model: m.id };
              const on = value.some((v) => same(v, t));
              return (
                <label key={m.id} className={`cursor-pointer rounded-lg border px-3 py-1.5 text-xs ${on ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 hover:bg-slate-50"}`}>
                  <input type="checkbox" className="sr-only" checked={on} onChange={() => toggle(t)} data-testid={`target-${m.id}`} />{m.id}
                </label>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export const selectedModels = (providers: Provider[], targets: Target[]) =>
  targets.map((t) => providers.find((p) => p.id === t.provider_id)?.models.find((m) => m.id === t.model)).filter(Boolean) as ModelCfg[];
