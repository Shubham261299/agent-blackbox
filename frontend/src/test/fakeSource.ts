import { vi } from "vitest";
import type { DataSource } from "../api/client";
import { SCENARIOS, comparison, evalReport, happyPathSpans, run, runEvaluation } from "./factories";

export function fakeSource(over: Partial<DataSource> = {}): DataSource {
  return {
    kind: "live",
    canStartRuns: true,
    canStartEvals: true,
    listRuns: vi.fn().mockResolvedValue([run()]),
    getRun: vi.fn().mockResolvedValue(run()),
    getSpans: vi.fn().mockResolvedValue(happyPathSpans()),
    listScenarios: vi.fn().mockResolvedValue(SCENARIOS),
    startRun: vi.fn().mockResolvedValue(run({ run_id: "run-new", status: "running", duration_ms: null })),
    listEvals: vi.fn().mockResolvedValue([evalReport()]),
    getEval: vi.fn().mockResolvedValue(evalReport()),
    compare: vi.fn().mockResolvedValue(comparison()),
    getRunEvaluation: vi.fn().mockResolvedValue(runEvaluation()),
    getRunFaults: vi.fn().mockResolvedValue([]),
    startEval: vi.fn().mockResolvedValue({ ...evalReport(), eval_id: "eval-new", status: "running", n_cases: 0, n_passed: 0 }),
    traceUrl: (id) => `http://jaeger.test/trace/${id}`,
    ...over,
  };
}
