import { ApiError, ApiUnreachableError, type DataSource } from "./client";
import type { Comparison, DemoManifest, EvalReport, EvalRunSummary, RunEvaluation, RunFault, RunRecord, ScenarioInfo, SpanRecord } from "./types";

interface ComparisonIndex {
  ok: Record<string, string>;
  refused: Record<string, string>;
}

const NOT_LIVE = "This demo shows recorded results and cannot start anything. To run an agent, clone the repository and start the app locally.";

/**
 * Serves the pages from the JSON files `python -m blackbox.export_demo` wrote, with the same answers and the same
 * refusals the live API gives. Every file is fetched at most once: the data is static.
 */
export function createDemoSource(base = "demo-data"): DataSource {
  const cache = new Map<string, Promise<unknown>>();

  function load<T>(path: string): Promise<T> {
    let pending = cache.get(path) as Promise<T> | undefined;
    if (!pending) {
      pending = fetchJson<T>(`${base}/${path}`);
      cache.set(path, pending);
      // A failure (offline, a file that is not there) must be retried next time, not remembered.
      pending.catch(() => cache.delete(path));
    }
    return pending;
  }

  async function fetchJson<T>(url: string): Promise<T> {
    let response: Response;
    try {
      response = await fetch(url);
    } catch {
      throw new ApiUnreachableError();
    }
    if (response.status === 404) throw new ApiError("not in this demo", 404);
    if (!response.ok) throw new ApiUnreachableError();
    return (await response.json()) as T;
  }

  async function requireRun(runId: string): Promise<RunRecord> {
    const run = (await load<RunRecord[]>("runs.json")).find((r) => r.run_id === runId);
    if (!run) throw new ApiError("run not found", 404);
    return run;
  }

  /** A file about one run: 404 from the server means this run is not in the demo. */
  async function ofRun<T>(runId: string, path: string): Promise<T> {
    await requireRun(runId);
    return load<T>(path);
  }

  const refuse = (): Promise<never> => Promise.reject(new ApiError(NOT_LIVE, 405));

  return {
    kind: "demo",
    canStartRuns: false,
    canStartEvals: false,
    listRuns: () => load<RunRecord[]>("runs.json"),
    getRun: requireRun,
    getSpans: (runId) => ofRun<SpanRecord[]>(runId, `spans/${encodeURIComponent(runId)}.json`),
    listScenarios: () => load<ScenarioInfo[]>("scenarios.json"),
    startRun: refuse,
    listEvals: () => load<EvalRunSummary[]>("evals.json"),
    getEval: async (evalId) => {
      const known = await load<EvalRunSummary[]>("evals.json");
      if (!known.some((e) => e.eval_id === evalId)) throw new ApiError("evaluation not found", 404);
      return load<EvalReport>(`evals/${encodeURIComponent(evalId)}.json`);
    },
    compare: async (baselineId, candidateId) => {
      const known = new Set((await load<EvalRunSummary[]>("evals.json")).map((e) => e.eval_id));
      const missing = [baselineId, candidateId].filter((id) => !known.has(id));
      if (missing.length > 0) throw new ApiError(`evaluation not found: ${missing.join(", ")}`, 404);
      const index = await load<ComparisonIndex>("comparisons/index.json");
      const key = `${baselineId}|${candidateId}`;
      const file = index.ok[key];
      if (file) return load<Comparison>(`comparisons/${file}`);
      throw new ApiError(index.refused[key] ?? "These two were not compared in this demo.", 422);
    },
    getRunEvaluation: (runId) => ofRun<RunEvaluation>(runId, `run-evaluations/${encodeURIComponent(runId)}.json`),
    getRunFaults: async (runId) => {
      await requireRun(runId);
      return (await load<Record<string, RunFault[]>>("faults.json"))[runId] ?? [];
    },
    startEval: refuse,
    // The trace is already on the page; there is no Jaeger behind a recorded demo.
    traceUrl: () => null,
    demoInfo: () => load<DemoManifest>("manifest.json"),
  };
}
