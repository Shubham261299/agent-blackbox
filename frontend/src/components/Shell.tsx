import type { ReactNode } from "react";
import { useTheme, type ThemePreference } from "../hooks/useTheme";
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

export function Shell({ children, demo }: { children: ReactNode; demo: boolean }) {
  const [theme, setTheme] = useTheme();
  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/" aria-label="Agent Blackbox, all runs">
            <BrandMark />
            <span className="brand-name">Agent Blackbox</span>
            <span className="brand-tag">Flight recorder for AI agents</span>
          </a>
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
    </div>
  );
}
