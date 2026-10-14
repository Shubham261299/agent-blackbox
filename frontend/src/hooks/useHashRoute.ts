import { useEffect, useState } from "react";

export type Route =
  | { name: "runs" }
  | { name: "run"; runId: string }
  | { name: "evals" }
  | { name: "eval"; evalId: string };

export function parseHash(hash: string): Route {
  const run = /^#\/runs\/([^/?#]+)/.exec(hash);
  if (run) return { name: "run", runId: decodeURIComponent(run[1] as string) };
  const evalRun = /^#\/evals\/([^/?#]+)/.exec(hash);
  if (evalRun) return { name: "eval", evalId: decodeURIComponent(evalRun[1] as string) };
  if (/^#\/evals\/?$/.test(hash)) return { name: "evals" };
  return { name: "runs" };
}

export const runHref = (runId: string) => `#/runs/${encodeURIComponent(runId)}`;
export const evalHref = (evalId: string) => `#/evals/${encodeURIComponent(evalId)}`;

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
