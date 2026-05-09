import type { Scenario } from "../scenarios";

interface Props {
  scenarios: readonly Scenario[];
  active: Scenario;
  onScenarioChange: (s: Scenario) => void;
  reachable: boolean | null;
}

export default function Header({
  scenarios,
  active,
  onScenarioChange,
  reachable,
}: Props) {
  return (
    <header className="flex items-center justify-between border-b border-ink/10 bg-paper px-6 py-4">
      <div className="flex items-baseline gap-3">
        <span className="text-2xl font-serif font-semibold text-ink">
          Hawiya AI
        </span>
        <span
          className="text-2xl text-crimson"
          style={{ fontFamily: "Amiri, Times New Roman, serif" }}
        >
          هوية
        </span>
        <span className="ml-3 text-xs uppercase tracking-widest text-ink/50">
          Sovereign Identity Intelligence · Demo
        </span>
      </div>

      <nav className="flex items-center gap-2">
        {scenarios.map((s) => {
          const isActive = s.id === active.id;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => onScenarioChange(s)}
              className={
                "rounded-full border px-4 py-1.5 text-sm font-medium transition " +
                (isActive
                  ? "border-crimson bg-crimson text-paper"
                  : "border-ink/15 bg-paper text-ink/70 hover:border-ink/40 hover:text-ink")
              }
            >
              <span className="mr-2 text-xs opacity-60">{s.id}</span>
              {s.pillLabel}
            </button>
          );
        })}
      </nav>

      <div className="flex items-center gap-2 text-xs">
        <span
          className={
            "h-2 w-2 rounded-full " +
            (reachable === null
              ? "bg-ink/20"
              : reachable
              ? "bg-teal"
              : "bg-crimson")
          }
          title={
            reachable === null
              ? "checking…"
              : reachable
              ? "API reachable"
              : "API not reachable"
          }
        />
        <span className="font-mono uppercase tracking-wide text-ink/60">
          {reachable === null ? "checking" : reachable ? "Live" : "Offline"}
        </span>
      </div>
    </header>
  );
}
