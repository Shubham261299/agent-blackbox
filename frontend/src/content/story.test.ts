import { describe, expect, it } from "vitest";
import { MANIFEST, COMPARISONS } from "../test/demoSource";
import { comparison, evalReport } from "../test/factories";
import { buildStory, storyText } from "./story";

const evals = [evalReport({ eval_id: "eval-hold", dataset_version: "holdout-v1", n_cases: 8 })];
const full = () => buildStory({ manifest: MANIFEST, evals, lab: COMPARISONS["eval-res"], bench: COMPARISONS["eval-guided"], second: COMPARISONS["eval-guided3"] });

describe("buildStory", () => {
  it("reads every figure from the stored results", () => {
    const s = full();
    expect(s.stats).toEqual(["173 recorded runs", "11 sets of results", "one small AI model on one laptop"]);
    const [failed, worked, didnt] = s.found;
    expect(failed?.big).toBe("Found the step");
    expect(worked?.big).toBe("3 of 4");
    expect(worked?.text).toContain("3 of the 4 problems I planted stopped mattering, and nothing got worse. The cost: 3 extra retries.");
    expect(didnt?.big).toBe("Fixed 2, broke 5");
    expect(didnt?.text).toContain("On 24 test cases it fixed 2 and broke 5. The original passed 19 of 24; the rewrite passed 16. A second attempt fixed 1 and broke 3.");
  });

  it("changes when the data changes, so nothing on the page is typed in", () => {
    const other = buildStory({
      manifest: { ...MANIFEST, counts: { ...MANIFEST.counts, runs: 9 } },
      evals: [evalReport({ eval_id: "eval-hold", n_cases: 12 })],
      lab: comparison({ matched: 6, fixed: 5, broken: 1 }),
      bench: comparison({ matched: 30, fixed: 7, broken: 2 }),
    });
    expect(other.stats[0]).toBe("9 recorded runs");
    expect(other.found[1]?.big).toBe("5 of 6");
    expect(other.found[1]?.text).toContain("1 got worse");
    expect(other.found[2]?.big).toBe("Fixed 7, broke 2");
    expect(other.honest[1]?.text).toContain("12 extra test cases");
  });

  it("uses singular words for one", () => {
    const s = buildStory({ manifest: MANIFEST, evals, lab: comparison({ matched: 1, fixed: 1, broken: 0, baseline_cost: { ...comparison().baseline_cost, retries: 0 }, candidate_cost: { ...comparison().candidate_cost, retries: 1 } }) });
    expect(s.found[1]?.text).toContain("1 of the 1 problem I planted");
    expect(s.found[1]?.text).toContain("1 extra retry.");
  });

  it("links each result to the page that shows it", () => {
    const hrefs = full().found.map((f) => f.href);
    expect(hrefs).toEqual(["#/runs/run-e92cfa5d", "#/compare/eval-lab/eval-res", "#/compare/eval-bench/eval-guided"]);
  });

  it("says a second attempt only when there was one", () => {
    const without = buildStory({ manifest: MANIFEST, evals, bench: COMPARISONS["eval-guided"] });
    expect(without.found.at(-1)?.text).not.toContain("second attempt");
    expect(full().found.at(-1)?.text).toContain("second attempt");
  });

  it("leaves out a result the data does not hold instead of showing an empty card", () => {
    expect(buildStory({ manifest: MANIFEST, evals }).found.map((f) => f.kicker)).toEqual(["I could see why it failed"]);
    expect(buildStory({ manifest: { ...MANIFEST, tour: {} }, evals }).found).toEqual([]);
  });

  it("does not invent how many cases were kept hidden", () => {
    const s = buildStory({ manifest: { ...MANIFEST, tour: { ...MANIFEST.tour, holdout: undefined } }, evals });
    expect(s.honest[1]?.text).toBe("I kept some extra test cases hidden from myself while I tuned the agent.");
    expect(s.honest[1]?.href).toBeUndefined();
  });

  it("lists the five honesty points and the limits, in first person", () => {
    const s = full();
    expect(s.honest).toHaveLength(5);
    expect(s.limits).toContain("It does not show how any other model behaves.");
    expect(storyText(s).some((t) => /\bI\b/.test(t))).toBe(true);
  });

  it("flattens to every sentence the page shows, with no empty strings", () => {
    const text = storyText(full());
    expect(text.length).toBeGreaterThan(30);
    expect(text.every((t) => t.trim().length > 0)).toBe(true);
    expect(text).toContain(full().title);
  });
});
