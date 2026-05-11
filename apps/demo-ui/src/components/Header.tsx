import type { Mode, Scenario } from "../scenarios";

interface Props {
  mode: Mode;
  onModeChange: (m: Mode) => void;
  scenarios: readonly Scenario[];
  active: Scenario;
  onScenarioChange: (s: Scenario) => void;
  reachable: boolean | null;
}

const MODES: Array<{ id: Mode; label: string; tagline: string }> = [
  {
    id: "wizsm",
    label: "Extract",
    tagline: "for consumers with their own registry (e.g. WizSM)",
  },
  {
    id: "registry",
    label: "Extract + Match",
    tagline: "for consumers using Hawiya's Person Registry",
  },
];

export default function Header({
  mode,
  onModeChange,
  scenarios,
  active,
  onScenarioChange,
  reachable,
}: Props) {
  return (
    <header className="border-b border-ink/10 bg-paper">
      <div className="flex items-center justify-between px-6 py-3">
        <div className="flex items-baseline gap-3">
          <span className="font-serif text-2xl font-semibold text-ink">
            Hawiya AI
          </span>
          <span className="font-arabic text-2xl text-crimson">هوية</span>
          <span className="ml-3 font-mono text-[11px] uppercase tracking-widest text-ink/50">
            Sovereign Identity Intelligence · Demo
          </span>
        </div>

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
          />
          <span className="font-mono uppercase tracking-wide text-ink/60">
            {reachable === null ? "checking" : reachable ? "Live" : "Offline"}
          </span>
        </div>
      </div>

      <div className="flex items-center justify-between gap-6 border-t border-ink/5 px-6 py-3">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] uppercase tracking-widest text-ink/50">
            View
          </span>
          <div className="flex overflow-hidden rounded border border-ink/15">
            {MODES.map((m) => {
              const isActive = m.id === mode;
              return (
                <button
                  key={m.id}
                  type="button"
                  title={m.tagline}
                  onClick={() => onModeChange(m.id)}
                  className={
                    "px-3 py-1 text-xs font-medium transition " +
                    (isActive
                      ? "bg-ink text-paper"
                      : "bg-paper text-ink/60 hover:bg-ink/5 hover:text-ink")
                  }
                >
                  {m.label}
                </button>
              );
            })}
          </div>
          <span className="ml-2 hidden font-sans text-[11px] text-ink/50 lg:inline">
            {MODES.find((m) => m.id === mode)?.tagline}
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
                  "rounded-full border px-4 py-1.5 text-xs font-medium transition " +
                  (isActive
                    ? "border-crimson bg-crimson text-paper"
                    : "border-ink/15 bg-paper text-ink/70 hover:border-ink/40 hover:text-ink")
                }
              >
                {s.pillLabel}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
