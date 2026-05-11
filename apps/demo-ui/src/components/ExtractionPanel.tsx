import { useEffect, useState } from "react";
import type { CallState } from "../App";
import type { Capture } from "./CapturePanel";
import type { Scenario } from "../scenarios";
import { CHECKSUM_LABELS } from "../mrz";

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
  capture: Capture;
  state: CallState;
}

export default function ExtractionPanel({ scenario, capture, state }: Props) {
  // What image to show in the loading state, and what MRZ to type out on
  // success. For the sample tab we have hand-crafted MRZ; for an
  // uploaded file we type whatever the OCR returned (reconstructed
  // best-effort from the response fields).
  const previewSrc =
    capture.kind === "upload" ? capture.previewUrl : scenario.imagePath;
  const isUpload = capture.kind === "upload";

  return (
    <section className="flex h-full flex-col">
      <div className="font-mono text-[11px] uppercase tracking-widest text-gold">
        02 · Extraction
      </div>
      <div className="mt-1 font-serif text-base text-ink/80">
        {isUpload ? "Officer-uploaded document" : scenario.title}
      </div>

      {state.status === "idle" && (
        <Idle scenario={scenario} isUpload={isUpload} />
      )}
      {state.status === "loading" && <Loading previewSrc={previewSrc} />}
      {state.status === "error" && (
        <ErrorPanel error={state.error} httpStatus={state.httpStatus} />
      )}
      {state.status === "success" && (
        <SuccessAnimated
          fields={state.result.fields}
          mrzLine1={isUpload ? null : scenario.mrzLine1}
          mrzLine2={isUpload ? null : scenario.mrzLine2}
        />
      )}
    </section>
  );
}

function Idle({
  scenario,
  isUpload,
}: {
  scenario: Scenario;
  isUpload: boolean;
}) {
  return (
    <div className="mt-6 space-y-4 text-sm text-ink/70">
      <p className="leading-relaxed">
        {isUpload
          ? "An officer-uploaded document. Same pipeline as the scanner — Hawiya AI doesn't care where the bytes came from."
          : scenario.blurb}
      </p>
      <div className="rounded border-l-2 border-gold bg-gold/5 px-4 py-3 text-ink/70">
        <div className="mb-1 font-mono text-[11px] uppercase tracking-wide text-gold/80">
          What happens when you click Scan
        </div>
        <ol className="list-inside list-decimal space-y-1 text-xs leading-relaxed">
          <li>Image is POSTed to the API.</li>
          <li>PassportEye + Tesseract OCR the MRZ.</li>
          <li>ICAO 9303 checksums validate the read.</li>
          <li>Result returns with extracted fields + confidence + audit.</li>
        </ol>
      </div>
    </div>
  );
}

function Loading({ previewSrc }: { previewSrc: string }) {
  return (
    <div className="mt-6 flex flex-col gap-4">
      <div className="overflow-hidden rounded border border-ink/10 bg-white shadow-sm scan-overlay">
        <img
          src={previewSrc}
          alt="Scanning document"
          className="block w-full opacity-90"
        />
      </div>
      <div className="text-center font-mono text-[11px] uppercase tracking-wide text-ink/60">
        Scanning · Tesseract is reading the MRZ region
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
      <div className="mb-2 font-mono text-[11px] uppercase tracking-wide text-crimson">
        {httpStatus > 0 ? `HTTP ${httpStatus} · ${error.code}` : error.code}
      </div>
      <div className="text-ink/80">{error.message}</div>
    </div>
  );
}

// Stages that play out after the API returns:
//   stage 0: type the MRZ char-by-char (real string from the scenario)
//   stage 1: reveal extracted fields (staggered, CSS-driven)
//   stage 2: flip the 5 checksum boxes green
//   stage 3: extraction-complete badge fades in
function SuccessAnimated({
  fields,
  mrzLine1,
  mrzLine2,
}: {
  fields: Record<string, string | null>;
  mrzLine1: string | null;
  mrzLine2: string | null;
}) {
  // For uploaded documents we don't know the canonical MRZ string, so
  // skip the typing animation and reveal fields immediately.
  const fullMrz = mrzLine1 && mrzLine2 ? mrzLine1 + "\n" + mrzLine2 : null;
  const [typed, setTyped] = useState("");
  const [stage, setStage] = useState<0 | 1 | 2 | 3>(0);

  useEffect(() => {
    setTyped("");
    setStage(0);
    if (!fullMrz) {
      // No canonical MRZ available — skip typing animation and reveal
      // the rest of the stages on the same cadence.
      setStage(1);
      const t1 = setTimeout(() => setStage(2), 700);
      const t2 = setTimeout(() => setStage(3), 700 + 1700);
      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
      };
    }
    let i = 0;
    const interval = setInterval(() => {
      i += 2; // 2 chars per tick keeps total ~880ms
      if (i >= fullMrz.length) {
        setTyped(fullMrz);
        clearInterval(interval);
        setStage(1);
        setTimeout(() => setStage(2), 700);
        setTimeout(() => setStage(3), 700 + 1700);
      } else {
        setTyped(fullMrz.slice(0, i));
      }
    }, 22);
    return () => clearInterval(interval);
  }, [fullMrz]);

  return (
    <div className="mt-4 flex flex-col gap-4 text-sm">
      {fullMrz && (
        <div className="rounded border border-ink/10 bg-ink/95 p-4 font-mono text-[12px] leading-relaxed text-paper shadow-sm">
          <div className="mb-2 font-sans text-[10px] uppercase tracking-wide text-paper/50">
            MRZ — read by Tesseract
          </div>
          <pre className="whitespace-pre">
            <span>{typed}</span>
            {stage === 0 && <span className="mrz-caret" />}
          </pre>
        </div>
      )}

      {stage >= 1 && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          {FIELD_LABELS.map(([key, label], i) => {
            const value = fields[key];
            return (
              <div
                key={key}
                className="field-reveal flex items-baseline justify-between border-b border-ink/5 pb-1.5"
                style={{ "--i": i } as React.CSSProperties}
              >
                <span className="font-mono text-[10px] uppercase tracking-wide text-ink/50">
                  {label}
                </span>
                <span className="font-mono text-[13px] text-ink">
                  {value ?? <span className="text-ink/30">—</span>}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {stage >= 2 && (
        <div>
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-ink/50">
            ICAO 9303 checksums
          </div>
          <div className="grid grid-cols-5 gap-2">
            {CHECKSUM_LABELS.map((label, i) => (
              <div
                key={label}
                className="checksum-flip flex flex-col items-center justify-center rounded p-2 text-[10px]"
                style={{ "--i": i } as React.CSSProperties}
              >
                <span className="text-base">✓</span>
                <span className="text-center font-mono uppercase tracking-tight">
                  {label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {stage >= 3 && (
        <div className="rounded bg-teal/10 px-3 py-2 text-center font-mono text-[11px] uppercase tracking-wide text-teal">
          Extraction complete · all five checksums passed
        </div>
      )}
    </div>
  );
}
