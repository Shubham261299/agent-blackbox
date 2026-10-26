import { vi } from "vitest";
import type { DataSource } from "../api/client";
import type { DemoManifest } from "../api/types";
import { comparison, evalReport } from "./factories";
import { fakeSource } from "./fakeSource";

export const MANIFEST: DemoManifest = {
  format: 1,
  models: ["ollama:qwen2.5:7b"],
  recorded_from: "2026-10-14",
  recorded_to: "2026-10-19",
  counts: { runs: 173, spans: 883, evaluations: 11, comparisons: 20, refused_pairs: 101 },
  evaluations: [],
  tour: {
    failed_run: "run-e92cfa5d",
    lab: "eval-lab",
    fixed: ["eval-lab", "eval-res"],
    regressed: ["eval-bench", "eval-guided"],
    second_attempt: ["eval-bench", "eval-guided3"],
    holdout: "eval-hold",
  },
};

const summary = (c: ReturnType<typeof comparison>, base: number, cand: number) => ({
  ...c,
  baseline: { ...c.baseline, n_passed: base, n_cases: c.matched },
  candidate: { ...c.candidate, n_passed: cand, n_cases: c.matched },
});

/** What the stored comparisons say, by candidate id: the numbers the README quotes. */
export const COMPARISONS: Record<string, ReturnType<typeof comparison>> = {
  "eval-res": comparison({ matched: 4, fixed: 3, broken: 0, kind: "faultlab", baseline_cost: { ...comparison().baseline_cost, retries: 0 }, candidate_cost: { ...comparison().candidate_cost, retries: 3 } }),
  "eval-guided": summary(comparison({ matched: 24, fixed: 2, broken: 5 }), 19, 16),
  "eval-guided3": summary(comparison({ matched: 24, fixed: 1, broken: 3 }), 19, 17),
};

/** A recorded-demo data source over fixed numbers, for the pages that only exist in the demo. */
export function demoSource(over: Partial<DataSource> = {}): DataSource {
  return fakeSource({
    kind: "demo",
    canStartRuns: false,
    canStartEvals: false,
    traceUrl: () => null,
    demoInfo: vi.fn().mockResolvedValue(MANIFEST),
    listEvals: vi.fn().mockResolvedValue([evalReport({ eval_id: "eval-hold", dataset_version: "holdout-v1", n_cases: 8, n_passed: 5 })]),
    compare: vi.fn().mockImplementation(async (_a: string, b: string) => {
      const found = COMPARISONS[b];
      if (!found) throw new Error(`no comparison for ${b}`);
      return found;
    }),
    ...over,
  });
}
