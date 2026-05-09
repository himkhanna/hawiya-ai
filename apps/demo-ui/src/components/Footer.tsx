import { config } from "../api";
import type { ResolveState } from "../App";

interface Props {
  state: ResolveState;
}

export default function Footer({ state }: Props) {
  const tenantShort = config.tenantId
    ? config.tenantId.slice(0, 8) + "…"
    : "(unset)";

  let timing = "—";
  if (state.status === "success") timing = `${state.durationMs} ms`;
  else if (state.status === "loading") timing = "in flight";

  return (
    <footer className="flex items-center justify-between border-t border-ink/10 bg-ink/5 px-6 py-2 font-mono text-[11px] text-ink/60">
      <div className="flex items-center gap-4">
        <span>v0.1 · /v1/identity/resolve</span>
        <span>tenant {tenantShort}</span>
        <span>baseUrl {new URL(config.baseUrl).host}</span>
      </div>
      <div className="flex items-center gap-4">
        <span>last call: {timing}</span>
        {state.status === "success" && (
          <span title={state.result.extraction_id}>
            extraction {state.result.extraction_id.slice(0, 8)}…
          </span>
        )}
      </div>
    </footer>
  );
}
