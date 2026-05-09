import type { Scenario } from "../scenarios";

interface Props {
  scenario: Scenario;
  onScan: () => void;
  busy: boolean;
}

export default function CapturePanel({ scenario, onScan, busy }: Props) {
  return (
    <section className="flex h-full flex-col">
      <PanelHeading
        index="01"
        title="Capture"
        subtitle="The document presented at the counter."
      />

      <div className="my-4 overflow-hidden rounded border border-ink/10 bg-white shadow-sm">
        <img
          src={scenario.imagePath}
          alt={`Specimen passport — scenario ${scenario.id}`}
          className="block w-full"
        />
      </div>

      <div className="mb-4 rounded bg-ink/5 px-3 py-2 text-xs leading-relaxed text-ink/70">
        <span className="mr-2 font-mono uppercase text-ink/60">Note</span>
        Synthetic specimen. Every field below is hand-rolled — no real
        traveller's data is shown anywhere in the demo.
      </div>

      <button
        type="button"
        onClick={onScan}
        disabled={busy}
        className={
          "mt-auto rounded bg-crimson px-4 py-3 text-sm font-medium uppercase tracking-wide text-paper transition " +
          (busy ? "cursor-wait opacity-60" : "hover:bg-crimson/90")
        }
      >
        {busy ? "Submitting to Hawiya AI…" : "Scan passport"}
      </button>
    </section>
  );
}

function PanelHeading({
  index,
  title,
  subtitle,
}: {
  index: string;
  title: string;
  subtitle: string;
}) {
  return (
    <div>
      <div className="font-mono text-xs uppercase tracking-widest text-gold">
        {index} · {title}
      </div>
      <div className="mt-1 text-sm text-ink/60">{subtitle}</div>
    </div>
  );
}
