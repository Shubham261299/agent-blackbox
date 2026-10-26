import type { ReactNode } from "react";
import { plainWords } from "../lib/plain";

/** "In plain words": a short box at the top of a page saying what you are looking at. Only in the recorded demo. */
export function PlainLead({ children }: { children: ReactNode }) {
  if (!plainWords()) return null;
  return (
    <aside className="plain-lead" aria-label="In plain words">
      <strong>In plain words</strong>
      <p>{children}</p>
    </aside>
  );
}

/**
 * The technical part of a page. In the recorded demo it is folded away behind a button, so the page opens on the plain
 * story and nothing is hidden for anyone who wants the detail. In the live app it is simply shown.
 */
export function Technical({ title = "Show technical details", children }: { title?: string; children: ReactNode }) {
  if (!plainWords()) return <>{children}</>;
  return (
    <details className="technical">
      <summary>{title}</summary>
      <div className="technical-body">{children}</div>
    </details>
  );
}
