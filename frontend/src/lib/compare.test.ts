import { describe, expect, it } from "vitest";
import type { EvalRunSummary } from "../api/types";
import { parseHash } from "../hooks/useHashRoute";
import { caseChange, comparison } from "../test/factories";
import { canCompare, comparableWith, costRows, delta, passCounts, sameAgent, variantLabel, verdict } from "./compare";

const summary = (over: Partial<EvalRunSummary> = {}): EvalRunSummary => ({
  eval_id: "eval-a", kind: "benchmark", model: "ollama:qwen2.5:7b", dataset_version: "golden-v3", dataset_hash: "h1", seed: 0, variant: "baseline",
  rescored_from: null, started_at: "2026-10-19T10:00:00Z", finished_at: "2026-10-19T10:04:00Z", status: "done", n_cases: 24, n_passed: 19, ...over,
});

describe("canCompare mirrors the backend's rules for a fair comparison", () => {
  const a = summary();
  it("accepts the same kind, model, dataset content and seed", () => {
    expect(canCompare(a, summary({ eval_id: "eval-b", variant: "resilient" }))).toBe(true);
  });
  it.each([
    ["itself", { eval_id: "eval-a" }],
    ["a different dataset content", { eval_id: "eval-b", dataset_hash: "h2" }],
    ["a different model", { eval_id: "eval-b", model: "ollama:other" }],
    ["a different seed", { eval_id: "eval-b", seed: 1 }],
    ["a different kind", { eval_id: "eval-b", kind: "faultlab" as const }],
    ["an unfinished evaluation", { eval_id: "eval-b", status: "running" as const }],
    ["a failed evaluation", { eval_id: "eval-b", status: "error" as const }],
  ])("refuses %s", (_name, over) => {
    expect(canCompare(a, summary(over))).toBe(false);
  });
  it("refuses an unfinished evaluation on either side", () => {
    expect(canCompare(summary({ status: "running" }), summary({ eval_id: "eval-b" }))).toBe(false);
    expect(canCompare(summary({ status: "error" }), summary({ eval_id: "eval-b" }))).toBe(false);
  });
  it("refuses the checks-validation kind: it checks the checks, not an agent", () => {
    expect(canCompare(summary({ kind: "validation" }), summary({ eval_id: "eval-b", kind: "validation" }))).toBe(false);
  });
  it("lists the compatible ones newest first and leaves the rest out", () => {
    const old = summary({ eval_id: "eval-old", started_at: "2026-10-01T00:00:00Z" });
    const fresh = summary({ eval_id: "eval-new", started_at: "2026-10-19T12:00:00Z" });
    const other = summary({ eval_id: "eval-other", dataset_hash: "zzz" });
    expect(comparableWith(a, [old, a, other, fresh]).map((e) => e.eval_id)).toEqual(["eval-new", "eval-old"]);
  });
});

describe("delta", () => {
  it("uses a real minus sign, an explicit plus, and words for nothing", () => {
    expect(delta(5, 8)).toBe("+3");
    expect(delta(8, 5)).toBe("−3");
    expect(delta(4, 4)).toBe("no change");
    expect(delta(10.04, 10.01, 1)).toBe("no change"); // below the shown precision
    expect(delta(10, 8.3, 1)).toBe("−1.7");
  });
});

describe("verdict counts what moved and never says improved", () => {
  const withCounts = (fixed: number, broken: number) => comparison({ fixed, broken, matched: 24 });
  it("reports a fix that broke nothing", () => {
    expect(verdict(withCounts(3, 0))).toMatchObject({ tone: "better", headline: "3 cases fixed, none broken" });
  });
  it("reports a regression with nothing gained", () => {
    expect(verdict(withCounts(0, 2))).toMatchObject({ tone: "worse", headline: "2 cases broken, none fixed" });
  });
  it("calls a trade mixed, with the net, even when more were fixed than broken", () => {
    const v = verdict(withCounts(3, 1));
    expect(v.tone).toBe("mixed");
    expect(v.headline).toBe("3 cases fixed, 1 case broken");
    expect(v.detail).toContain("net +2");
    expect(verdict(withCounts(2, 5)).detail).toContain("net −3");
    expect(verdict(withCounts(2, 2)).detail).toContain("net zero");
  });
  it("says so when nothing changed", () => {
    expect(verdict(withCounts(0, 0))).toMatchObject({ tone: "same", headline: "Nothing changed" });
  });
  it("talks about faults for a failure-lab comparison", () => {
    expect(verdict(comparison({ kind: "faultlab", fixed: 3, broken: 0, matched: 4 })).headline).toBe("3 faults fixed, none broken");
    expect(verdict(comparison({ kind: "faultlab", fixed: 1, broken: 0, matched: 4 })).headline).toBe("1 fault fixed, none broken");
  });
});

describe("passCounts", () => {
  it("counts only the cases both sides ran", () => {
    const c = comparison({
      cases: [
        caseChange({ case_id: "a", change: "fixed", baseline_passed: false, candidate_passed: true }),
        caseChange({ case_id: "b", change: "still_passing" }),
        caseChange({ case_id: "c", change: "only_baseline", baseline_passed: true, candidate_passed: null }),
        caseChange({ case_id: "d", change: "only_candidate", baseline_passed: null, candidate_passed: true }),
      ],
    });
    expect(passCounts(c)).toEqual({ before: 1, after: 2, total: 2 });
  });
});

describe("costRows", () => {
  it("shows tokens only when both sides measured them, and never invents them", () => {
    const c = comparison();
    expect(costRows(c.baseline_cost, c.candidate_cost).map((r) => r.label)).toContain("Prompt tokens");
    const unmeasured = costRows({ ...c.baseline_cost, input_tokens: null, output_tokens: null }, c.candidate_cost);
    expect(unmeasured.map((r) => r.label)).not.toContain("Prompt tokens");
    expect(unmeasured.map((r) => r.label)).not.toContain("Reply tokens");
  });
  it("puts the median next to a warning that the total includes stalls", () => {
    const c = comparison();
    const rows = Object.fromEntries(costRows(c.baseline_cost, c.candidate_cost).map((r) => [r.label, r]));
    expect(rows["Tool calls"]).toMatchObject({ before: "10", after: "7", change: "−3" });
    expect(rows["Median run time"]?.note).toMatch(/fair/);
    expect(rows["Total run time"]?.note).toMatch(/stall/);
    expect(rows["Median run time"]?.change).toBe("−2.0 s");
  });
});

describe("variants and the compare route", () => {
  it("names the known variants and shows an unknown one as it is", () => {
    expect(variantLabel("resilient")).toBe("Resilient");
    expect(variantLabel("guided-v3")).toBe("Guided (v3)");
    expect(variantLabel("something-new")).toBe("something-new");
  });
  it("knows when both sides are the same agent", () => {
    expect(sameAgent(comparison())).toBe(false);
    const c = comparison();
    expect(sameAgent({ ...c, candidate: { ...c.candidate, variant: "baseline" } })).toBe(true);
  });
  it("parses #/compare/<before>/<after> and not the evaluation routes", () => {
    expect(parseHash("#/compare/eval-a/eval-b")).toEqual({ name: "compare", baseline: "eval-a", candidate: "eval-b" });
    expect(parseHash("#/compare/eval%20a/eval-b")).toEqual({ name: "compare", baseline: "eval a", candidate: "eval-b" });
    expect(parseHash("#/compare/eval-a")).toEqual({ name: "home" }); // incomplete: falls back to the landing page
    expect(parseHash("#/evals/eval-a")).toEqual({ name: "eval", evalId: "eval-a" });
  });
});
