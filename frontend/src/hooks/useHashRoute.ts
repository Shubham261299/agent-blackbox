import { useEffect, useState } from "react";

export type Route =
  | { name: "home" }
  | { name: "runs" }
  | { name: "run"; runId: string }
  | { name: "evals" }
  | { name: "eval"; evalId: string }
  | { name: "compare"; baseline: string; candidate: string };

export function parseHash(hash: string): Route {
  const run = /^#\/runs\/([^/?#]+)/.exec(hash);
  if (run) return { name: "run", runId: decodeURIComponent(run[1] as string) };
  const compare = /^#\/compare\/([^/?#]+)\/([^/?#]+)/.exec(hash);
  if (compare) return { name: "compare", baseline: decodeURIComponent(compare[1] as string), candidate: decodeURIComponent(compare[2] as string) };
  const evalRun = /^#\/evals\/([^/?#]+)/.exec(hash);
  if (evalRun) return { name: "eval", evalId: decodeURIComponent(evalRun[1] as string) };
  if (/^#\/evals\/?$/.test(hash)) return { name: "evals" };
  if (/^#\/runs\/?$/.test(hash)) return { name: "runs" };
  return { name: "home" }; // the front page; the live app shows its run list there
}

export const HOME_HREF = "#/";
export const RUNS_HREF = "#/runs";
export const runHref = (runId: string) => `#/runs/${encodeURIComponent(runId)}`;
export const evalHref = (evalId: string) => `#/evals/${encodeURIComponent(evalId)}`;
export const compareHref = (baselineId: string, candidateId: string) =>
  `#/compare/${encodeURIComponent(baselineId)}/${encodeURIComponent(candidateId)}`;

/** Hash routing keeps the app deployable as plain static files (the Day 6 demo). */
export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
