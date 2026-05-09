import { useEffect, useState } from "react";
import {
  ApiCallError,
  config,
  resolveIdentity,
  type ApiError,
  type ResolveResult,
} from "./api";
import { SCENARIOS, loadScenarioImage, type Scenario } from "./scenarios";
import Header from "./components/Header";
import CapturePanel from "./components/CapturePanel";
import ExtractionPanel from "./components/ExtractionPanel";
import ResolutionPanel from "./components/ResolutionPanel";
import Footer from "./components/Footer";

export type ResolveState =
  | { status: "idle" }
  | { status: "loading"; startedAt: number }
  | { status: "success"; result: ResolveResult; durationMs: number }
  | { status: "error"; error: ApiError; httpStatus: number };

export default function App() {
  const [scenario, setScenario] = useState<Scenario>(SCENARIOS[0]);
  const [state, setState] = useState<ResolveState>({ status: "idle" });
  const [reachable, setReachable] = useState<boolean | null>(null);

  // Probe /v1/health on mount so the live indicator in the header is
  // honest. Re-probe whenever the user changes scenarios (cheap).
  useEffect(() => {
    let cancelled = false;
    fetch(`${config.baseUrl}/v1/health`)
      .then((r) => !cancelled && setReachable(r.ok))
      .catch(() => !cancelled && setReachable(false));
    return () => {
      cancelled = true;
    };
  }, []);

  // Reset the result panel whenever the user switches scenarios.
  function handleScenarioChange(next: Scenario): void {
    setScenario(next);
    setState({ status: "idle" });
  }

  async function handleScan(): Promise<void> {
    setState({ status: "loading", startedAt: performance.now() });
    try {
      const blob = await loadScenarioImage(scenario);
      const result = await resolveIdentity(blob, `${scenario.id}.jpg`);
      const durationMs = Math.round(
        performance.now() -
          (state.status === "loading" ? state.startedAt : performance.now())
      );
      setState({ status: "success", result, durationMs });
    } catch (e) {
      if (e instanceof ApiCallError) {
        setState({
          status: "error",
          error: e.body.error ?? {
            code: "UNKNOWN",
            message: e.message,
          },
          httpStatus: e.status,
        });
      } else {
        setState({
          status: "error",
          error: { code: "UNKNOWN", message: (e as Error).message },
          httpStatus: 0,
        });
      }
    }
  }

  return (
    <div className="flex h-screen flex-col bg-paper text-ink">
      <Header
        scenarios={SCENARIOS}
        active={scenario}
        onScenarioChange={handleScenarioChange}
        reachable={reachable}
      />
      <main className="grid flex-1 grid-cols-12 gap-px overflow-hidden bg-ink/10">
        <div className="col-span-3 overflow-y-auto bg-paper p-6">
          <CapturePanel
            scenario={scenario}
            onScan={handleScan}
            busy={state.status === "loading"}
          />
        </div>
        <div className="col-span-5 overflow-y-auto bg-paper p-6">
          <ExtractionPanel scenario={scenario} state={state} />
        </div>
        <div className="col-span-4 overflow-y-auto bg-paper p-6">
          <ResolutionPanel scenario={scenario} state={state} />
        </div>
      </main>
      <Footer state={state} />
    </div>
  );
}
