import { describe, expect, it } from "vitest";
import { comparison } from "../test/factories";
import { parseTour, tourLink, tourStops, withoutTour } from "./tour";

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
    expect(worked?.text).toContain("Of 4 planted problems, 3 now have no effect on the run and 0 were made worse, at a cost of 3 extra retries.");
    expect(didnt?.text).toContain("On 24 cases it fixed 2 and broke 5.");
  });

  it("uses the singular where there is one", () => {
    const one = comparison({ matched: 1, fixed: 1, broken: 1, baseline_cost: { ...comparison().baseline_cost, retries: 2 }, candidate_cost: { ...comparison().candidate_cost, retries: 3 } });
    const [, , worked, didnt] = tourStops(TOUR, one, one);
    expect(worked?.text).toContain("Of 1 planted problem, 1 now has no effect on the run and 1 was made worse, at a cost of 1 extra retry.");
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

describe("tour addresses", () => {
  const stops = tourStops(TOUR, lab, bench);

  it("marks an address with the stop number and reads it back", () => {
    expect(tourLink(stops[2] as (typeof stops)[number], 2)).toBe("#/compare/eval-lab-base/eval-lab-res?tour=3");
    expect(parseTour("#/compare/eval-lab-base/eval-lab-res?tour=3")).toBe(3);
    expect(parseTour("#/runs/run-1?x=1&tour=12")).toBe(12);
  });

  it("says nothing about the tour for an address that is not part of it", () => {
    expect(parseTour("#/runs/run-1")).toBeNull();
    expect(parseTour("#/runs/run-1?tour=")).toBeNull();
    expect(parseTour("#/runs/run-1?detour=2")).toBeNull();
    expect(parseTour("")).toBeNull();
  });

  it("takes the marker back off", () => {
    expect(withoutTour("#/runs/run-1?tour=2")).toBe("#/runs/run-1");
    expect(withoutTour("#/runs/run-1")).toBe("#/runs/run-1");
    expect(withoutTour("#/a?x=1&tour=2")).toBe("#/a?x=1");
  });

  it("gives every stop something to look at, in words a newcomer can follow", () => {
    for (const stop of stops) expect(stop.notice.length).toBeGreaterThan(40);
    expect(stops.map((s) => s.notice).join(" ")).toContain("Where to look first");
  });

  it("round-trips: every stop's address parses back to its own number", () => {
    stops.forEach((stop, i) => expect(parseTour(tourLink(stop, i))).toBe(i + 1));
  });
});
