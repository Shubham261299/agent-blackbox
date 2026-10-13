import { useCallback, useEffect, useState } from "react";

export type ThemePreference = "system" | "light" | "dark";
const KEY = "blackbox.theme";

function readStored(): ThemePreference {
  // ?theme=dark in the URL wins; handy for screenshots and sharing a view
  try {
    const fromUrl = new URLSearchParams(window.location.search).get("theme");
    if (fromUrl === "light" || fromUrl === "dark") return fromUrl;
    const stored = window.localStorage.getItem(KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    /* storage can be blocked; fall through to the default */
  }
  return "system";
}

function apply(pref: ThemePreference) {
  const root = document.documentElement;
  if (pref === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", pref);
}

export function useTheme(): [ThemePreference, (next: ThemePreference) => void] {
  const [pref, setPref] = useState<ThemePreference>(readStored);
  useEffect(() => apply(pref), [pref]);
  const set = useCallback((next: ThemePreference) => {
    setPref(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      /* not persisted; still applied for this session */
    }
  }, []);
  return [pref, set];
}
