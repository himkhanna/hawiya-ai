import { useEffect, useMemo, useRef, useState } from "react";
import type { Scenario } from "../scenarios";

// What's currently in the capture buffer:
//   sample : one of the pre-baked scenario JPEGs (default)
//   upload : a file the officer dragged or browsed for
export type Capture =
  | { kind: "sample" }
  | { kind: "upload"; file: File; name: string; previewUrl: string };

interface Props {
  scenario: Scenario;
  capture: Capture;
  onCaptureChange: (c: Capture) => void;
  onScan: () => void;
  busy: boolean;
}

// Backend accepts JPEG / PNG / TIFF / PDF. PDFs are rasterised (page 1)
// before OCR. HEIC is rejected server-side with a clear message.
const ACCEPTED = "image/jpeg,image/png,image/tiff,application/pdf";
const MAX_BYTES = 10 * 1024 * 1024;

export default function CapturePanel({
  scenario,
  capture,
  onCaptureChange,
  onScan,
  busy,
}: Props) {
  const [tab, setTab] = useState<"sample" | "upload">(
    capture.kind === "upload" ? "upload" : "sample"
  );
  const [error, setError] = useState<string | null>(null);

  // If capture is reset to "sample" by an external action (header pill
  // change, view-mode toggle), flip the tab back. Only depend on
  // capture.kind — depending on `tab` would race against the user
  // clicking the Upload tab (capture is still "sample" at that point
  // so it would immediately flip back).
  useEffect(() => {
    if (capture.kind === "sample") setTab("sample");
  }, [capture.kind]);

  function handleFiles(files: FileList | null): void {
    setError(null);
    if (!files || files.length === 0) return;
    const file = files[0];
    if (file.size > MAX_BYTES) {
      setError(`File too large (${Math.round(file.size / 1024)} KB; max 10 MB)`);
      return;
    }
    if (
      !ACCEPTED.split(",").some((t) => file.type === t || file.type === "")
    ) {
      setError(
        `Unsupported file type: ${file.type || "unknown"}. Use JPEG, PNG, TIFF, or PDF.`
      );
      return;
    }
    const previewUrl = URL.createObjectURL(file);
    onCaptureChange({
      kind: "upload",
      file,
      name: file.name,
      previewUrl,
    });
  }

  return (
    <section className="flex h-full flex-col">
      <div className="font-mono text-[11px] uppercase tracking-widest text-gold">
        01 · Capture
      </div>
      <div className="mt-1 font-serif text-base text-ink/80">
        Document presented at the counter
      </div>

      <div className="mt-4 flex overflow-hidden rounded border border-ink/15 text-xs">
        <TabButton
          active={tab === "sample"}
          onClick={() => {
            setTab("sample");
            onCaptureChange({ kind: "sample" });
          }}
        >
          Sample (scanner)
        </TabButton>
        <TabButton
          active={tab === "upload"}
          onClick={() => setTab("upload")}
        >
          Upload
        </TabButton>
      </div>

      {tab === "sample" ? (
        <SamplePane scenario={scenario} />
      ) : (
        <UploadPane
          capture={capture}
          onFiles={handleFiles}
          error={error}
          onClear={() => {
            onCaptureChange({ kind: "sample" });
            setTab("sample");
          }}
        />
      )}

      <button
        type="button"
        onClick={onScan}
        disabled={busy || (tab === "upload" && capture.kind !== "upload")}
        className={
          "mt-auto rounded bg-crimson px-4 py-3 text-sm font-medium uppercase tracking-wide text-paper transition " +
          (busy || (tab === "upload" && capture.kind !== "upload")
            ? "cursor-not-allowed opacity-50"
            : "hover:bg-crimson/90")
        }
      >
        {busy
          ? "Submitting to Hawiya AI…"
          : tab === "upload" && capture.kind !== "upload"
          ? "Drop or browse a file first"
          : "Scan passport"}
      </button>
    </section>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "flex-1 px-3 py-2 font-medium transition " +
        (active
          ? "bg-ink text-paper"
          : "bg-paper text-ink/60 hover:bg-ink/5 hover:text-ink")
      }
    >
      {children}
    </button>
  );
}

function SamplePane({ scenario }: { scenario: Scenario }) {
  return (
    <>
      <div className="my-4 overflow-hidden rounded border border-ink/10 bg-white shadow-sm">
        <img
          src={scenario.imagePath}
          alt={`Specimen passport — ${scenario.pillLabel}`}
          className="block w-full"
        />
      </div>
      <div className="mb-4 rounded bg-ink/5 px-3 py-2 text-xs leading-relaxed text-ink/70">
        <span className="mr-2 font-mono uppercase text-ink/60">Note</span>
        Synthetic specimen. Stands in for a real document scanner output
        (e.g. Regula). Every byte is hand-rolled.
      </div>
    </>
  );
}

function UploadPane({
  capture,
  onFiles,
  error,
  onClear,
}: {
  capture: Capture;
  onFiles: (files: FileList | null) => void;
  error: string | null;
  onClear: () => void;
}) {
  const [hover, setHover] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const upload = useMemo(
    () => (capture.kind === "upload" ? capture : null),
    [capture]
  );

  return (
    <>
      {upload ? (
        <div className="my-4 space-y-3">
          <div className="overflow-hidden rounded border border-ink/10 bg-white shadow-sm">
            {upload.file.type === "application/pdf" ? (
              <div className="flex h-48 flex-col items-center justify-center bg-ink/5 p-4 text-center text-xs text-ink/60">
                <div className="mb-1 font-mono uppercase tracking-wide text-ink/50">
                  PDF
                </div>
                <div>
                  PDFs are rasterised (page 1, 200 DPI) before OCR.
                  Preview not shown — the backend reads it as-is.
                </div>
              </div>
            ) : (
              <img
                src={upload.previewUrl}
                alt={upload.name}
                className="block max-h-72 w-full object-contain"
              />
            )}
          </div>
          <div className="flex items-center justify-between gap-2 text-xs">
            <div className="min-w-0 flex-1">
              <div className="truncate font-mono text-ink">{upload.name}</div>
              <div className="text-ink/50">
                {(upload.file.size / 1024).toFixed(1)} KB ·{" "}
                {upload.file.type || "unknown"}
              </div>
            </div>
            <button
              type="button"
              onClick={onClear}
              className="rounded border border-ink/15 px-2 py-1 text-[10px] uppercase tracking-wide text-ink/60 hover:border-ink/40 hover:text-ink"
            >
              Clear
            </button>
          </div>
        </div>
      ) : (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setHover(true);
          }}
          onDragLeave={() => setHover(false)}
          onDrop={(e) => {
            e.preventDefault();
            setHover(false);
            onFiles(e.dataTransfer.files);
          }}
          onClick={() => inputRef.current?.click()}
          className={
            "my-4 flex h-56 cursor-pointer flex-col items-center justify-center rounded border-2 border-dashed text-sm transition " +
            (hover
              ? "border-crimson bg-crimson/5 text-crimson"
              : "border-ink/20 bg-ink/5 text-ink/60 hover:border-ink/40")
          }
        >
          <div className="mb-2 font-mono text-[11px] uppercase tracking-wide">
            Drop a document
          </div>
          <div className="text-xs">or click to browse</div>
          <div className="mt-3 text-[11px] text-ink/40">
            JPEG · PNG · TIFF · PDF · max 10 MB
          </div>
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        className="hidden"
        onChange={(e) => onFiles(e.target.files)}
      />

      {error && (
        <div className="mb-3 rounded border border-crimson/30 bg-crimson/5 px-3 py-2 text-xs text-crimson">
          {error}
        </div>
      )}

      <div className="mb-4 rounded bg-teal/5 px-3 py-2 text-xs leading-relaxed text-ink/70">
        <span className="mr-2 font-mono uppercase text-teal">Real flow</span>
        The bytes you drop here are POSTed to Hawiya AI exactly as a
        scanner would. Real documents never leave your environment.
      </div>
    </>
  );
}
