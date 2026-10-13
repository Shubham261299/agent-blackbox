import { vi } from "vitest";
import type { DataSource } from "../api/client";
import { SCENARIOS, happyPathSpans, run } from "./factories";

export function fakeSource(over: Partial<DataSource> = {}): DataSource {
  return {
    kind: "live",
    canStartRuns: true,
    listRuns: vi.fn().mockResolvedValue([run()]),
    getRun: vi.fn().mockResolvedValue(run()),
    getSpans: vi.fn().mockResolvedValue(happyPathSpans()),
    listScenarios: vi.fn().mockResolvedValue(SCENARIOS),
    startRun: vi.fn().mockResolvedValue(run({ run_id: "run-new", status: "running", duration_ms: null })),
    traceUrl: (id) => `http://jaeger.test/trace/${id}`,
    ...over,
  };
}
