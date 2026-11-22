import { Icon } from "./StudioVisuals";

export function ViewToggle({
  value,
  onChange,
}: {
  value: "grid" | "list";
  onChange: (v: "grid" | "list") => void;
}) {
  return (
    <div className="view-toggle" role="group" aria-label="Visualização">
      {(
        [
          ["grid", "Galeria"],
          ["list", "Lista"],
        ] as const
      ).map(([key, label]) => (
        <button
          type="button"
          key={key}
          onClick={() => onChange(key)}
          aria-label={label}
          aria-pressed={value === key}
        >
          <Icon name={key} size={18} />
        </button>
      ))}
    </div>
  );
}

export function FactoryFilter({
  value,
  onChange,
  options,
  label = "Filtrar por fábrica",
}: {
  value: string;
  onChange: (v: string) => void;
  options: { id: string; name: string }[];
  label?: string;
}) {
  return (
    <label className="collection-select">
      <Icon name="factory" size={16} />
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="all">Todas as fábricas</option>
        {options.map((f) => (
          <option value={f.id} key={f.id}>
            {f.name}
          </option>
        ))}
      </select>
    </label>
  );
}
