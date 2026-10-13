import { useEffect, useState } from "react";

export type Route = { name: "runs" } | { name: "run"; runId: string };

export function parseHash(hash: string): Route {
  const match = /^#\/runs\/([^/?#]+)/.exec(hash);
  return match ? { name: "run", runId: decodeURIComponent(match[1] as string) } : { name: "runs" };
}

export const runHref = (runId: string) => `#/runs/${encodeURIComponent(runId)}`;

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
