import type { ReactNode } from "react";
import type { Route } from "../hooks/useHashRoute";
import { useTheme, type ThemePreference } from "../hooks/useTheme";
import { AboutDemo } from "./AboutDemo";
import { Icon } from "./Icon";

const THEMES: { value: ThemePreference; label: string; icon: "monitor" | "sun" | "moon" }[] = [
  { value: "system", label: "System theme", icon: "monitor" },
  { value: "light", label: "Light theme", icon: "sun" },
  { value: "dark", label: "Dark theme", icon: "moon" },
];

function BrandMark() {
  // Flight-recorder orange; the three bars are a tiny trace waterfall.
  return (
    <svg className="brand-mark" width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="7" fill="#f26a1b" />
      <rect x="7" y="9" width="18" height="4" rx="2" fill="#fff" />
      <rect x="7" y="15" width="11" height="4" rx="2" fill="#fff" opacity=".85" />
      <rect x="12" y="21" width="13" height="4" rx="2" fill="#fff" opacity=".7" />
    </svg>
  );
}

export function Shell({ children, demo, route }: { children: ReactNode; demo: boolean; route: Route }) {
  const [theme, setTheme] = useTheme();
  // The live app opens on its run list; the recorded demo opens on a front page and keeps the run list one click away.
  const inHome = demo && route.name === "home";
  const inRuns = route.name === "run" || route.name === "runs" || (!demo && route.name === "home");
  const inEvals = route.name === "evals" || route.name === "eval";
  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/" aria-label={demo ? "Agent Blackbox, front page" : "Agent Blackbox, all runs"}>
            <BrandMark />
            <span className="brand-name">Agent Blackbox</span>
            <span className="brand-tag">Flight recorder for AI agents</span>
          </a>
          <nav className="nav" aria-label="Main">
            {demo && (
              <a href="#/" aria-current={inHome ? "page" : undefined}>
                Overview
              </a>
            )}
            <a href={demo ? "#/runs" : "#/"} aria-current={inRuns ? "page" : undefined}>
              Runs
            </a>
            <a href="#/evals" aria-current={inEvals ? "page" : undefined}>
              Evaluations
            </a>
          </nav>
          <div className="topbar-right">
            <span className="local-note" title="Runs, traces and evaluations stay on this machine.">
              <Icon name="lock" size={13} />
              {demo ? "Recorded demo data" : "Local only"}
            </span>
            <div className="seg" role="radiogroup" aria-label="Theme">
              {THEMES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  role="radio"
                  aria-checked={theme === t.value}
                  aria-label={t.label}
                  title={t.label}
                  className="seg-btn"
                  onClick={() => setTheme(t.value)}
                >
                  <Icon name={t.icon} size={15} />
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>
      <main className="page">{children}</main>
      {demo && <AboutDemo />}
    </div>
  );
}
