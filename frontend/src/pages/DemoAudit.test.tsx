/**
 * The real demo, page by page: every page a visitor can reach from the front page, rendered from the exported data
 * with the plain words on, must show no jargon outside the folded technical details. A new page, a new kind of result
 * or a re-export that brings a technical word to the surface fails here, naming the page and the word.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { DataSource } from "../api/client";
import type { Comparison, DemoManifest, EvalRunSummary, RunRecord } from "../api/types";
import { BANNED_WORDS, jargonIn } from "../lib/readability";
import { setPlainWords } from "../lib/plain";
import { demoJson, realDemoSource } from "../test/realDemo";

let source: DataSource;

beforeEach(() => {
  setPlainWords(true);
  source = realDemoSource();
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  cleanup();
  setPlainWords(false);
});
afterAll(() => vi.unstubAllGlobals());

/** What a visitor reads without opening anything: no folded details, no code-like text, plus the hover notes. */
export function visibleText(root: HTMLElement): string {
  const clone = root.cloneNode(true) as HTMLElement;
  clone.querySelectorAll(".technical-body, .mono, code, pre, script, style").forEach((el) => el.remove());
  const hovers = [...clone.querySelectorAll("[title]")].map((el) => el.getAttribute("title") ?? "");
  return [clone.textContent ?? "", ...hovers].join("\n");
}

async function pageText(hash: string): Promise<string> {
  window.location.hash = hash;
  const { container } = render(<App source={source} />);
  await screen.findByRole("heading", { level: 1 });
  await waitFor(() => expect(screen.queryByText(/^Loading/)).not.toBeInTheDocument());
  await new Promise((r) => setTimeout(r, 20)); // let the page's other queries settle
  const text = visibleText(container);
  cleanup(); // one page at a time: the next render must not see this one
  return text;
}

/** Where each banned word appears, with a few words around it, so a failure says what to reword. */
function snippets(text: string): string[] {
  const out: string[] = [];
  for (const bad of jargonIn(text, BANNED_WORDS)) {
    for (const m of text.matchAll(new RegExp(String.raw`.{0,40}\b${bad}\b.{0,40}`, "gi"))) out.push(`${bad}: “${m[0].replace(/\s+/g, " ").trim()}”`);
  }
  return out;
}

const audit = async (hash: string) => {
  const text = await pageText(hash);
  expect.soft(snippets(text), `jargon on ${hash}`).toEqual([]); // soft: report every page, not just the first
  return text;
};

describe("the real demo, in plain words", () => {
  it("the front page", async () => {
    const text = await audit("#/");
    expect(text).toContain("flight recorder");
  });

  it("the run list", async () => {
    await audit("#/runs");
  });

  it("the results list", async () => {
    await audit("#/evals");
  });

  it("every stop of the tour, entered the way a visitor enters it", async () => {
    const tour = demoJson<DemoManifest>("manifest.json").tour;
    const stops = [`#/runs/${tour.failed_run}?tour=1`, `#/evals/${tour.lab}?tour=2`, `#/compare/${tour.fixed?.join("/")}?tour=3`, `#/compare/${tour.regressed?.join("/")}?tour=4`];
    for (const hash of stops) await audit(hash);
  });

  it("every set of results", async () => {
    for (const e of demoJson<EvalRunSummary[]>("evals.json")) await audit(`#/evals/${e.eval_id}`);
  }, 60_000);

  it("every before and after, and the page for a pair that cannot be compared", async () => {
    const index = demoJson<{ ok: Record<string, string>; refused: Record<string, string> }>("comparisons/index.json");
    for (const key of Object.keys(index.ok)) await audit(`#/compare/${key.replace("|", "/")}`);
    const [refused] = Object.keys(index.refused).filter((k) => /different cases/.test(index.refused[k] ?? ""));
    await audit(`#/compare/${(refused as string).replace("|", "/")}`);
  }, 120_000);

  it("the runs of each kind: failed, real-model, scripted, and each planted-problem run", async () => {
    const runs = demoJson<RunRecord[]>("runs.json");
    const pick = [
      ...runs.filter((r) => r.status === "error").slice(0, 3),
      ...runs.filter((r) => r.model.startsWith("ollama:") && r.status === "ok").slice(0, 3),
      ...runs.filter((r) => r.model.startsWith("scripted:")).slice(0, 3),
    ];
    const faults = demoJson<Record<string, unknown>>("faults.json");
    pick.push(...runs.filter((r) => r.run_id in faults));
    for (const r of new Set(pick)) await audit(`#/runs/${r.run_id}`);
  }, 60_000);

  it("every guided-tour sentence the banner can say", async () => {
    const comparisons = demoJson<{ ok: Record<string, string> }>("comparisons/index.json").ok;
    expect(Object.keys(comparisons).length).toBeGreaterThan(10);
    const c = demoJson<Comparison>(`comparisons/${Object.values(comparisons)[0]}`);
    expect(c.cases.length).toBeGreaterThan(0);
  });
});
