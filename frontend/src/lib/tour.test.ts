import { describe, expect, it } from "vitest";
import { comparison } from "../test/factories";
import { tourStops } from "./tour";

const TOUR = {
  failed_run: "run-e92cfa5d",
  lab: "eval-lab-base",
  fixed: ["eval-lab-base", "eval-lab-res"] as [string, string],
  regressed: ["eval-bench-base", "eval-bench-guided"] as [string, string],
};
const lab = comparison({ matched: 4, fixed: 3, broken: 0, baseline_cost: { ...comparison().baseline_cost, retries: 0 }, candidate_cost: { ...comparison().candidate_cost, retries: 3 } });
const bench = comparison({ matched: 24, fixed: 2, broken: 5 });

describe("tourStops", () => {
  it("has the four stops in the order a visitor should see them, each linking to its page", () => {
    const stops = tourStops(TOUR, lab, bench);
    expect(stops.map((s) => s.title)).toEqual(["A run that failed", "The failure lab", "A fix that worked", "A fix that did not"]);
    expect(stops.map((s) => s.href)).toEqual([
      "#/runs/run-e92cfa5d",
      "#/evals/eval-lab-base",
      "#/compare/eval-lab-base/eval-lab-res",
      "#/compare/eval-bench-base/eval-bench-guided",
    ]);
  });

  it("reads the numbers of the two before-and-after stops from the comparisons", () => {
    const [, , worked, didnt] = tourStops(TOUR, lab, bench);
    expect(worked?.text).toContain("Of 4 planted faults, 3 now have no effect on the run and 0 were made worse, at a cost of 3 extra retries.");
    expect(didnt?.text).toContain("On 24 cases it fixed 2 and broke 5.");
  });

  it("uses the singular where there is one", () => {
    const one = comparison({ matched: 1, fixed: 1, broken: 1, baseline_cost: { ...comparison().baseline_cost, retries: 2 }, candidate_cost: { ...comparison().candidate_cost, retries: 3 } });
    const [, , worked, didnt] = tourStops(TOUR, one, one);
    expect(worked?.text).toContain("Of 1 planted fault, 1 now has no effect on the run and 1 was made worse, at a cost of 1 extra retry.");
    expect(didnt?.text).toContain("On 1 case it fixed 1 and broke 1.");
  });

  it("never reports a negative cost", () => {
    const cheaper = comparison({ matched: 4, baseline_cost: { ...comparison().baseline_cost, retries: 5 }, candidate_cost: { ...comparison().candidate_cost, retries: 1 } });
    expect(tourStops(TOUR, cheaper)[2]?.text).toContain("0 extra retries");
  });

  it("says what a page shows, without any number, until its comparison has loaded or when it could not", () => {
    const stops = tourStops(TOUR);
    expect(stops).toHaveLength(4);
    for (const stop of stops.slice(2)) expect(stop.text).not.toMatch(/\d/);
  });

  it("leaves out a stop the data does not hold", () => {
    expect(tourStops({})).toEqual([]);
    expect(tourStops({ failed_run: "run-1" }).map((s) => s.title)).toEqual(["A run that failed"]);
    expect(tourStops({ fixed: TOUR.fixed }, lab).map((s) => s.title)).toEqual(["A fix that worked"]);
  });

  it("encodes ids in links", () => {
    expect(tourStops({ failed_run: "run a/b" })[0]?.href).toBe("#/runs/run%20a%2Fb");
  });
});
