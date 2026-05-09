import type { ResolveState } from "../App";
import type { Scenario } from "../scenarios";
import type { ResolveResult } from "../api";

interface Props {
  scenario: Scenario;
  state: ResolveState;
}

export default function ResolutionPanel({ scenario, state }: Props) {
  return (
    <section className="flex h-full flex-col">
      <div className="font-mono text-xs uppercase tracking-widest text-gold">
        03 · Identity resolution
      </div>
      <div className="mt-1 text-sm text-ink/60">
        Hawiya AI's recommendation
      </div>

      {state.status === "idle" && <Idle scenario={scenario} />}
      {state.status === "success" && <ResultCard result={state.result} />}
      {state.status === "loading" && (
        <div className="mt-10 text-center text-xs text-ink/40">
          waiting for extraction…
        </div>
      )}
      {state.status === "error" && (
        <div className="mt-10 text-center text-xs text-ink/40">
          (no decision — extraction failed)
        </div>
      )}

      {/* The talk-track is for the operator giving the demo, not the audience. */}
      <details className="mt-auto rounded border border-ink/10 bg-ink/5 p-3 text-xs text-ink/70">
        <summary className="cursor-pointer font-mono uppercase tracking-wide text-ink/50">
          Operator talk-track ({scenario.id})
        </summary>
        <ul className="mt-2 list-inside list-disc space-y-1 leading-relaxed">
          {scenario.talkTrack.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}

function Idle({ scenario }: { scenario: Scenario }) {
  return (
    <div className="mt-6 rounded border border-dashed border-ink/15 p-4 text-sm text-ink/40">
      Press <span className="font-medium">Scan passport</span> to see the
      decision for the <span className="font-medium">{scenario.pillLabel}</span>{" "}
      scenario.
    </div>
  );
}

function ResultCard({ result }: { result: ResolveResult }) {
  const action = result.action;
  const display = ACTION_DISPLAY[action];
  const confPct = Math.round(result.confidence * 100);

  return (
    <div className="mt-4 space-y-4">
      <div
        className={
          "rounded border p-4 " +
          (display.tone === "go"
            ? "border-teal/40 bg-teal/5"
            : display.tone === "review"
            ? "border-gold/40 bg-gold/5"
            : "border-ink/15 bg-paper")
        }
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className={
                "text-lg " +
                (display.tone === "go"
                  ? "text-teal"
                  : display.tone === "review"
                  ? "text-gold"
                  : "text-ink/70")
              }
            >
              {display.icon}
            </span>
            <span className="font-mono text-xs uppercase tracking-widest">
              {display.heading}
            </span>
          </div>
          <span className="font-mono text-xs text-ink/60">
            confidence {confPct}%
          </span>
        </div>
        <p className="mt-2 text-sm text-ink/80">{display.body}</p>
      </div>

      <div className="rounded border border-ink/10 p-4 text-sm">
        <div className="mb-1 font-mono text-xs uppercase tracking-wide text-ink/50">
          Person record
        </div>
        <div className="font-medium text-ink">
          {fullName(result.fields) || "(no name extracted)"}
        </div>
        <div className="mt-2 grid grid-cols-2 gap-y-1 text-xs text-ink/60">
          <span>UUID</span>
          <span className="truncate font-mono text-ink">
            {result.person_uuid?.slice(0, 18) ?? "—"}…
          </span>
          <span>Nationality</span>
          <span className="font-mono text-ink">
            {result.fields.nationality ?? "—"}
          </span>
          <span>Date of birth</span>
          <span className="font-mono text-ink">
            {result.fields.date_of_birth ?? "—"}
          </span>
          <span>Method</span>
          <span className="font-mono text-ink">{result.method}</span>
        </div>
      </div>

      <details className="rounded border border-ink/10 p-3 text-xs text-ink/70">
        <summary className="cursor-pointer font-mono uppercase tracking-wide text-ink/50">
          Audit trail
        </summary>
        <div className="mt-2 grid grid-cols-2 gap-y-1">
          <span>Decision</span>
          <span className="font-mono">{action}</span>
          <span>Confidence</span>
          <span className="font-mono">{result.confidence.toFixed(2)}</span>
          <span>Method</span>
          <span className="font-mono">{result.method}</span>
          <span>Extraction id</span>
          <span className="truncate font-mono">{result.extraction_id}</span>
        </div>
        <div className="mt-2 text-[10px] text-ink/50">
          The full audit row is also written to the audit_log table — the
          customer's auditors query it directly.
        </div>
      </details>
    </div>
  );
}

function fullName(fields: Record<string, string | null>): string {
  const given = (fields.given_names ?? "").trim();
  const surname = (fields.surname ?? "").trim();
  return [given, surname].filter(Boolean).join(" ").replace(/\s+/g, " ");
}

interface Display {
  heading: string;
  body: string;
  icon: string;
  tone: "go" | "review" | "neutral";
}

const ACTION_DISPLAY: Record<string, Display> = {
  new_record: {
    heading: "New person created",
    body: "No existing record matched. A Golden Record was just created in the Person Registry.",
    icon: "+",
    tone: "go",
  },
  auto_matched: {
    heading: "Matched to existing record",
    body: "We've seen this person before. No duplicate created.",
    icon: "✓",
    tone: "go",
  },
  suggested_match: {
    heading: "Possible duplicate — review required",
    body: "Some fields match an existing person but others don't. Routed to officer review. The system will not auto-link.",
    icon: "⚠",
    tone: "review",
  },
  manual_review: {
    heading: "Manual review (Phase 2)",
    body: "Probabilistic match below auto-merge threshold. Officer decides.",
    icon: "?",
    tone: "review",
  },
  no_match_no_create: {
    heading: "No match, no record created",
    body: "Nothing in the registry matched, and the caller asked us not to create.",
    icon: "—",
    tone: "neutral",
  },
};
