import type { Comparison, DemoManifest } from "../api/types";
import { compareHref, evalHref, runHref } from "../hooks/useHashRoute";

export interface TourStop {
  title: string;
  href: string;
  text: string;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/**
 * The four stops of the "Start here" card. The ids come from the exported data, and every number in a sentence is read
 * from the stored comparison, never typed in: until a comparison has loaded its sentence says what the page shows
 * without a number. A stop the data does not hold is left out.
 */
export function tourStops(tour: DemoManifest["tour"], fixed?: Comparison, regressed?: Comparison): TourStop[] {
  const stops: TourStop[] = [];
  if (tour.failed_run) {
    stops.push({
      title: "A run that failed",
      href: runHref(tour.failed_run),
      text: "A real run where a tool did not answer in time. The trace shows the step that failed in red, and “Where to look first” names it.",
    });
  }
  if (tour.lab) {
    stops.push({
      title: "The failure lab",
      href: evalHref(tour.lab),
      text: "Four faults were planted on purpose. Three stop the run or break a rule; one raises no error at all, and only a check on the tool’s output notices it.",
    });
  }
  if (tour.fixed) {
    const [before, after] = tour.fixed;
    stops.push({
      title: "A fix that worked",
      href: compareHref(before, after),
      text: fixed
        ? `Retrying a failed step. Of ${plural(fixed.matched, "planted fault", "planted faults")}, ${fixed.fixed} now ${fixed.fixed === 1 ? "has" : "have"} no effect on the run and ${fixed.broken} ${fixed.broken === 1 ? "was" : "were"} made worse, at a cost of ${plural(Math.max(0, fixed.candidate_cost.retries - fixed.baseline_cost.retries), "extra retry", "extra retries")}.`
        : "Retrying a failed step. The page shows what was fixed, what got worse, and what it cost.",
    });
  }
  if (tour.regressed) {
    const [before, after] = tour.regressed;
    stops.push({
      title: "A fix that did not",
      href: compareHref(before, after),
      text: regressed
        ? `A better prompt looked like an improvement. On ${plural(regressed.matched, "case", "cases")} it fixed ${regressed.fixed} and broke ${regressed.broken}. The page shows exactly which cases got worse.`
        : "A better prompt looked like an improvement. The page shows which cases it fixed and which it broke.",
    });
  }
  return stops;
}
