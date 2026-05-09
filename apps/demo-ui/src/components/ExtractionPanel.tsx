import type { ResolveState } from "../App";
import type { Scenario } from "../scenarios";

const FIELD_LABELS: Array<[key: string, label: string]> = [
  ["document_type", "Document type"],
  ["issuing_country", "Issuing country"],
  ["document_number", "Passport number"],
  ["surname", "Surname"],
  ["given_names", "Given names"],
  ["nationality", "Nationality"],
  ["date_of_birth", "Date of birth"],
  ["sex", "Sex"],
  ["date_of_expiry", "Date of expiry"],
];

interface Props {
  scenario: Scenario;
  state: ResolveState;
}

export default function ExtractionPanel({ scenario, state }: Props) {
  return (
    <section className="flex h-full flex-col">
      <div className="font-mono text-xs uppercase tracking-widest text-gold">
        02 · Extraction
      </div>
      <div className="mt-1 text-sm text-ink/60">{scenario.title}</div>

      {state.status === "idle" && <Idle scenario={scenario} />}
      {state.status === "loading" && <Loading />}
      {state.status === "error" && (
        <ErrorPanel error={state.error} httpStatus={state.httpStatus} />
      )}
      {state.status === "success" && <Fields fields={state.result.fields} />}
    </section>
  );
}

function Idle({ scenario }: { scenario: Scenario }) {
  return (
    <div className="mt-6 space-y-4 text-sm text-ink/70">
      <p className="leading-relaxed">{scenario.blurb}</p>
      <div className="rounded border-l-2 border-gold bg-gold/5 px-4 py-3 text-ink/70">
        <div className="mb-1 font-mono text-xs uppercase text-gold/80">
          What happens when you click Scan
        </div>
        <ol className="list-inside list-decimal space-y-1 text-xs leading-relaxed">
          <li>Image is POSTed to /v1/identity/resolve.</li>
          <li>PassportEye + Tesseract OCR the MRZ.</li>
          <li>ICAO 9303 checksums validate the read.</li>
          <li>Deterministic matcher checks the Person Registry.</li>
          <li>Result returns with action + confidence + audit.</li>
        </ol>
      </div>
    </div>
  );
}

function Loading() {
  return (
    <div className="mt-10 flex flex-col items-center gap-3 text-sm text-ink/60">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-ink/20 border-t-crimson" />
      <div className="font-mono text-xs uppercase tracking-wide">
        Calling /v1/identity/resolve
      </div>
      <div className="text-xs text-ink/40">
        Tesseract is doing real OCR — typically 0.5-1.5 seconds.
      </div>
    </div>
  );
}

function ErrorPanel({
  error,
  httpStatus,
}: {
  error: { code: string; message: string };
  httpStatus: number;
}) {
  return (
    <div className="mt-6 rounded border border-crimson/30 bg-crimson/5 p-4 text-sm">
      <div className="mb-2 font-mono text-xs uppercase tracking-wide text-crimson">
        {httpStatus > 0 ? `HTTP ${httpStatus} · ${error.code}` : error.code}
      </div>
      <div className="text-ink/80">{error.message}</div>
    </div>
  );
}

function Fields({ fields }: { fields: Record<string, string | null> }) {
  return (
    <div className="mt-4 space-y-2 text-sm">
      {FIELD_LABELS.map(([key, label]) => {
        const value = fields[key];
        return (
          <div
            key={key}
            className="flex items-baseline justify-between border-b border-ink/5 pb-2"
          >
            <span className="font-mono text-xs uppercase tracking-wide text-ink/50">
              {label}
            </span>
            <span className="font-mono text-sm text-ink">
              {value ?? <span className="text-ink/30">—</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
}
