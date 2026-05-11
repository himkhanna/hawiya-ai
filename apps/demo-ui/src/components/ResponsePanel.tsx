// Right-column panel for WizSM mode. Where the registry view shows
// match decisions, this view shows the structured JSON payload that
// WizSM's engineering team consumes — they take it from here and run
// their own dedup against the Diwan's registry.

import { isExtractResult, type CallState } from "../App";
import type { Scenario } from "../scenarios";
import type { ExtractResult } from "../api";

interface Props {
  scenario: Scenario;
  state: CallState;
}

export default function ResponsePanel({ scenario, state }: Props) {
  return (
    <section className="flex h-full flex-col">
      <div className="font-mono text-[11px] uppercase tracking-widest text-gold">
        03 · Response payload
      </div>
      <div className="mt-1 font-serif text-base text-ink/80">
        What WizSM receives
      </div>

      {state.status === "idle" && <Idle scenario={scenario} />}
      {state.status === "loading" && (
        <div className="mt-10 text-center text-xs text-ink/40">
          waiting for extraction…
        </div>
      )}
      {state.status === "error" && (
        <div className="mt-10 text-center text-xs text-ink/40">
          (no payload — extraction failed)
        </div>
      )}
      {state.status === "success" && isExtractResult(state.result) && (
        <SuccessJson result={state.result} />
      )}

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
    <div className="mt-6 space-y-3 text-sm text-ink/60">
      <p className="leading-relaxed">
        Press{" "}
        <span className="font-medium text-ink">Scan passport</span> to see the
        JSON Hawiya AI returns for this {scenario.pillLabel.toLowerCase()}.
      </p>
      <p className="rounded border-l-2 border-teal/60 bg-teal/5 px-3 py-2 text-xs leading-relaxed">
        WizSM consumes this payload, runs its own duplicate check against the
        Diwan's registry, and stores the record. Hawiya itself does not store
        WizSM's persons in this configuration.
      </p>
    </div>
  );
}

function SuccessJson({ result }: { result: ExtractResult }) {
  const overallConfidence = avgConfidence(result.confidence_per_field);
  const conf = Math.round(overallConfidence * 100);

  return (
    <div className="mt-4 flex flex-col gap-3 text-sm">
      <div className="flex items-center justify-between text-xs">
        <span className="font-mono uppercase tracking-wide text-ink/50">
          checksum_status
        </span>
        <ChecksumBadge value={result.checksum_status} />
      </div>
      <div className="flex items-center justify-between text-xs">
        <span className="font-mono uppercase tracking-wide text-ink/50">
          overall confidence
        </span>
        <span className="font-mono text-ink">{conf}%</span>
      </div>
      <div className="flex items-center justify-between text-xs">
        <span className="font-mono uppercase tracking-wide text-ink/50">
          processing_time_ms
        </span>
        <span className="font-mono text-ink">
          {result.processing_time_ms} ms
        </span>
      </div>

      <div className="rounded border border-ink/10 bg-ink/95 p-3 text-paper shadow-sm">
        <div className="mb-2 flex items-center justify-between font-sans text-[10px] uppercase tracking-wide text-paper/50">
          <span>JSON · POST /v1/documents/extract</span>
          <span className="rounded border border-paper/20 px-2 py-0.5 text-[9px]">
            sent to consumer
          </span>
        </div>
        <pre className="overflow-x-auto whitespace-pre font-mono text-[11px] leading-relaxed">
          {prettyJson(result)}
        </pre>
      </div>

      <details className="rounded border border-ink/10 p-3 text-xs text-ink/70">
        <summary className="cursor-pointer font-mono uppercase tracking-wide text-ink/50">
          Audit log entry
        </summary>
        <div className="mt-2 grid grid-cols-2 gap-y-1">
          <span>Endpoint</span>
          <span className="font-mono">/v1/documents/extract</span>
          <span>Extraction id</span>
          <span className="truncate font-mono">{result.extraction_id}</span>
          <span>Document type</span>
          <span className="font-mono">{result.document_type}</span>
          <span>Processing path</span>
          <span className="font-mono">{result.processing_path}</span>
          <span>Confidence</span>
          <span className="font-mono">{overallConfidence.toFixed(2)}</span>
        </div>
        <div className="mt-2 text-[10px] text-ink/50">
          Hawiya logs every read of every document. Auditors query the
          tenant-scoped audit_log table directly.
        </div>
      </details>
    </div>
  );
}

function ChecksumBadge({ value }: { value: ExtractResult["checksum_status"] }) {
  const tone =
    value === "all_pass"
      ? "border-teal/40 bg-teal/10 text-teal"
      : value === "partial"
      ? "border-gold/40 bg-gold/10 text-gold"
      : value === "all_fail"
      ? "border-crimson/40 bg-crimson/10 text-crimson"
      : "border-ink/15 bg-ink/5 text-ink/50";
  return (
    <span
      className={
        "rounded border px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide " +
        tone
      }
    >
      {value}
    </span>
  );
}

// Render the API response with the core fields first so a customer can
// scan it quickly. Stable key order, two-space indent.
const KEY_ORDER = [
  "extraction_id",
  "document_type",
  "checksum_status",
  "processing_path",
  "processing_time_ms",
  "fields",
  "confidence_per_field",
];

function prettyJson(obj: ExtractResult): string {
  const ordered: Record<string, unknown> = {};
  for (const k of KEY_ORDER) {
    const v = (obj as unknown as Record<string, unknown>)[k];
    if (v !== undefined) ordered[k] = v;
  }
  return JSON.stringify(ordered, null, 2);
}

function avgConfidence(c: Record<string, number>): number {
  const xs = Object.values(c);
  if (!xs.length) return 0;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}
