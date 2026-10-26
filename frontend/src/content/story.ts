import type { Comparison, DemoManifest, EvalRunSummary } from "../api/types";
import { compareHref, evalHref, runHref } from "../hooks/useHashRoute";

export const REPO_URL = "https://github.com/Shubham261299/agent-blackbox";

export interface StoryData {
  manifest: DemoManifest;
  evals: EvalRunSummary[];
  /** Baseline against the retrying agent, on the failure lab. */
  lab?: Comparison;
  /** Baseline against the first rewritten instructions, on the 24 cases. */
  bench?: Comparison;
  /** Baseline against the second rewrite. */
  second?: Comparison;
}

export interface FoundCard {
  kicker: string;
  big: string;
  text: string;
  href: string;
  linkText: string;
}

export interface Story {
  title: string;
  intro: string;
  stats: string[];
  problemTitle: string;
  problem: string[];
  builtTitle: string;
  built: { title: string; text: string }[];
  foundTitle: string;
  found: FoundCard[];
  honestTitle: string;
  honest: { text: string; href?: string; linkText?: string }[];
  limitsTitle: string;
  limits: string;
  insideTitle: string;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/**
 * Everything the front page says. The words are fixed; every number is read from the stored results, so a page that
 * says "3 of 4" can only say it while the stored comparison says so. Kept free of React so it can be tested as text.
 */
export function buildStory({ manifest, evals, lab, bench, second }: StoryData): Story {
  const tour = manifest.tour;
  const holdout = tour.holdout ? evals.find((e) => e.eval_id === tour.holdout) : undefined;

  const found: FoundCard[] = [];
  if (tour.failed_run) {
    found.push({
      kicker: "I could see why it failed",
      big: "Found the step",
      text: "A tool did not answer in time, so the agent stopped before finishing a refund. The page names the step to look at first.",
      href: runHref(tour.failed_run),
      linkText: "See the failed run",
    });
  }
  if (tour.fixed && lab) {
    const extra = Math.max(0, lab.candidate_cost.retries - lab.baseline_cost.retries);
    found.push({
      kicker: "A fix that worked",
      big: `${lab.fixed} of ${lab.matched}`,
      text: `I taught the agent to try a failed step again. ${lab.fixed} of the ${plural(lab.matched, "problem", "problems")} I planted stopped mattering, and ${lab.broken === 0 ? "nothing" : lab.broken} got worse. The cost: ${plural(extra, "extra retry", "extra retries")}.`,
      href: compareHref(tour.fixed[0], tour.fixed[1]),
      linkText: "See the before and after",
    });
  }
  if (tour.regressed && bench) {
    const again = second
      ? ` A second attempt fixed ${second.fixed} and broke ${second.broken}.`
      : "";
    found.push({
      kicker: "A fix that did not work",
      big: `Fixed ${bench.fixed}, broke ${bench.broken}`,
      text: `I rewrote the agent's instructions and it looked like an improvement. On ${plural(bench.matched, "test case", "test cases")} it fixed ${bench.fixed} and broke ${bench.broken}. The original passed ${bench.baseline.n_passed} of ${bench.matched}; the rewrite passed ${bench.candidate.n_passed}.${again}`,
      href: compareHref(tour.regressed[0], tour.regressed[1]),
      linkText: "See which ones broke",
    });
  }

  const hidden = holdout ? `${holdout.n_cases} extra test cases` : "some extra test cases";
  return {
    title: "AI agents can fail without anyone noticing. I built a flight recorder that shows where, and tests whether a fix really works.",
    intro:
      "This is a small customer-support AI agent, a recorder for everything it does, automatic checks, and honest before-and-after results. Everything on this site is a recording of real runs on a laptop. Nothing here is live.",
    stats: [
      `${manifest.counts.runs} recorded runs`,
      `${manifest.counts.evaluations} sets of results`,
      "one small AI model on one laptop",
    ],
    problemTitle: "The problem, in one minute",
    problem: [
      "When a plane has an accident, the black box tells investigators what happened.",
      "AI agents now do real work, like issuing refunds. When one gets it wrong, usually nobody can say why. And nobody can say whether the fix helped. That is the gap this project fills.",
    ],
    builtTitle: "What I built",
    built: [
      { title: "The agent", text: "A support assistant that looks up orders, checks the refund rules and issues refunds. It runs on a small AI model on my own laptop." },
      { title: "The recorder", text: "It writes down every step the agent takes, with timing and errors, and hides personal details." },
      { title: "The checks", text: "Plain pass-or-fail rules, such as “did it finish the job?” and “did it break a rule?”, run on every recording." },
      { title: "The comparison", text: "It puts two versions side by side and counts what got fixed and what got broken." },
    ],
    foundTitle: "What I found",
    found,
    honestTitle: "How I made sure the numbers are honest",
    honest: [
      {
        text: "I wrote down what I expected before each real run.",
        href: `${REPO_URL}/blob/main/docs/day-5-fix-and-compare-plan.md`,
        linkText: "See the written predictions",
      },
      {
        text: `I kept ${hidden} hidden from myself while I tuned the agent.`,
        href: tour.holdout ? evalHref(tour.holdout) : undefined,
        linkText: tour.holdout ? "See that test" : undefined,
      },
      {
        text: "I checked the checker. Two of my own failures were correct answers that my rules did not recognise. I fixed the rules in the open, and never the test.",
        href: `${REPO_URL}/blob/main/BRIEF.md`,
        linkText: "Read what went wrong",
      },
      { text: "I report what got worse, not only what got better." },
      { text: "Every version is judged by the same test, and the site refuses to compare two things that were tested differently." },
    ],
    limitsTitle: "What this cannot tell you",
    limits:
      "One small model, one laptop, a few dozen test cases, and problems I planted myself. It shows that the method works. It does not show how any other model behaves.",
    insideTitle: "Look inside",
  };
}

/** Every sentence the page shows, flattened, for checks on the words themselves. */
export function storyText(s: Story): string[] {
  return [
    s.title,
    s.intro,
    ...s.stats,
    s.problemTitle,
    ...s.problem,
    s.builtTitle,
    ...s.built.flatMap((b) => [b.title, b.text]),
    s.foundTitle,
    ...s.found.flatMap((f) => [f.kicker, f.big, f.text, f.linkText]),
    s.honestTitle,
    ...s.honest.flatMap((h) => [h.text, h.linkText ?? ""]).filter(Boolean),
    s.limitsTitle,
    s.limits,
    s.insideTitle,
  ];
}
