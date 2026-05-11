import { useEffect, useMemo, useState } from "react";
import {
  ApiCallError,
  config,
  extractDocument,
  resolveIdentity,
  type ApiError,
  type ExtractResult,
  type ResolveResult,
} from "./api";
import {
  scenariosFor,
  loadScenarioImage,
  type Mode,
  type Scenario,
} from "./scenarios";
import Header from "./components/Header";
import CapturePanel, { type Capture } from "./components/CapturePanel";
import ExtractionPanel from "./components/ExtractionPanel";
import ResolutionPanel from "./components/ResolutionPanel";
import ResponsePanel from "./components/ResponsePanel";
import Footer from "./components/Footer";

export type CallState =
  | { status: "idle" }
  | { status: "loading"; startedAt: number }
  | {
      status: "success";
      result: ResolveResult | ExtractResult;
      durationMs: number;
    }
  | { status: "error"; error: ApiError; httpStatus: number };

// Type guard so panels can switch on the response shape.
export function isExtractResult(
  r: ResolveResult | ExtractResult
): r is ExtractResult {
  return (r as ExtractResult).checksum_status !== undefined;
}

const DEFAULT_MODE: Mode = "wizsm";

export default function App() {
  const [mode, setMode] = useState<Mode>(DEFAULT_MODE);
  const visible = useMemo(() => scenariosFor(mode), [mode]);
  const [scenario, setScenario] = useState<Scenario>(visible[0]);
  // Capture: either a built-in scenario sample or a user-uploaded file.
  const [capture, setCapture] = useState<Capture>({ kind: "sample" });
  const [state, setState] = useState<CallState>({ status: "idle" });
  const [reachable, setReachable] = useState<boolean | null>(null);

  // Reset to first scenario + sample mode whenever the view toggles.
  useEffect(() => {
    setScenario(scenariosFor(mode)[0]);
    setCapture({ kind: "sample" });
    setState({ status: "idle" });
  }, [mode]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${config.baseUrl}/v1/health`)
      .then((r) => !cancelled && setReachable(r.ok))
      .catch(() => !cancelled && setReachable(false));
    return () => {
      cancelled = true;
    };
  }, []);

  function handleScenarioChange(next: Scenario): void {
    setScenario(next);
    setCapture({ kind: "sample" });
    setState({ status: "idle" });
  }

  async function handleScan(): Promise<void> {
    const startedAt = performance.now();
    setState({ status: "loading", startedAt });
    try {
      let blob: Blob;
      let filename: string;
      if (capture.kind === "upload") {
        blob = capture.file;
        filename = capture.name;
      } else {
        blob = await loadScenarioImage(scenario);
        filename = `${scenario.id}.jpg`;
      }
      const result =
        mode === "wizsm"
          ? await extractDocument(blob, filename)
          : await resolveIdentity(blob, filename);
      const durationMs = Math.round(performance.now() - startedAt);
      setState({ status: "success", result, durationMs });
    } catch (e) {
      if (e instanceof ApiCallError) {
        setState({
          status: "error",
          error: e.body.error ?? { code: "UNKNOWN", message: e.message },
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
        mode={mode}
        onModeChange={setMode}
        scenarios={visible}
        active={scenario}
        onScenarioChange={handleScenarioChange}
        reachable={reachable}
      />
      <main className="grid flex-1 grid-cols-12 gap-px overflow-hidden bg-ink/10">
        <div className="col-span-3 overflow-y-auto bg-paper p-6">
          <CapturePanel
            scenario={scenario}
            capture={capture}
            onCaptureChange={(c) => {
              setCapture(c);
              setState({ status: "idle" });
            }}
            onScan={handleScan}
            busy={state.status === "loading"}
          />
        </div>
        <div className="col-span-5 overflow-y-auto bg-paper p-6">
          <ExtractionPanel
            scenario={scenario}
            capture={capture}
            state={state}
          />
        </div>
        <div className="col-span-4 overflow-y-auto bg-paper p-6">
          {mode === "wizsm" ? (
            <ResponsePanel scenario={scenario} state={state} />
          ) : (
            <ResolutionPanel scenario={scenario} state={state} />
          )}
        </div>
      </main>
      <Footer state={state} mode={mode} />
    </div>
  );
}
