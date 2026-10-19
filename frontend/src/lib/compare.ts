import type { CaseChangeKind, Comparison, CostTotals, EvalRunSummary } from "../api/types";
import { formatDuration } from "./timeScale";

const COMPARABLE_KINDS = ["benchmark", "reference", "faultlab"];

/** The agent configurations the project defines, in plain words. An unknown name is shown as it is. */
export const VARIANT_INFO: Record<string, { label: string; what: string }> = {
  baseline: { label: "Baseline", what: "The agent as first built: no retries, no output checks, the original prompt." },
  resilient: { label: "Resilient", what: "Retries a timeout or a model failure up to twice, and rejects a tool answer that breaks its contract and tries again." },
  guided: { label: "Guided (v2)", what: "A new system prompt and new tool descriptions telling the model to look the order up first and to ask instead of invent." },
  full: { label: "Full (v2)", what: "Resilient and Guided (v2) together." },
  "guided-v3": { label: "Guided (v3)", what: "A second attempt at the new prompt and tool descriptions, written after v2 made things worse." },
  "full-v3": { label: "Full (v3)", what: "Resilient and Guided (v3) together." },
};

export function variantLabel(variant: string): string {
  return VARIANT_INFO[variant]?.label ?? variant;
}

/**
 * Mirrors the backend's rules for a fair comparison, so the picker only offers evaluations that can work. The API
 * still decides (and says why in words); this just avoids offering a choice that is bound to be refused.
 */
export function canCompare(a: EvalRunSummary, b: EvalRunSummary): boolean {
  return (
    a.eval_id !== b.eval_id &&
    a.status === "done" &&
    b.status === "done" &&
    COMPARABLE_KINDS.includes(a.kind) &&
    a.kind === b.kind &&
    a.dataset_hash === b.dataset_hash &&
    a.model === b.model &&
    a.seed === b.seed
  );
}

/** Evaluations that can be compared with `current`, newest first. */
export function comparableWith(current: EvalRunSummary, all: EvalRunSummary[]): EvalRunSummary[] {
  return all.filter((e) => canCompare(current, e)).sort((x, y) => y.started_at.localeCompare(x.started_at));
}

export const CHANGE_LABEL: Record<CaseChangeKind, string> = {
  fixed: "Fixed",
  broken: "Broken",
  still_passing: "Still passing",
  still_failing: "Still failing",
  only_baseline: "Only in baseline",
  only_candidate: "Only in candidate",
};

/** The same sign convention everywhere: a real minus sign, an explicit plus, and nothing for no change. */
export function delta(before: number, after: number, digits = 0): string {
  const d = after - before;
  const rounded = Number(d.toFixed(digits));
  if (rounded === 0) return "no change";
  return `${rounded > 0 ? "+" : "−"}${Math.abs(rounded).toFixed(digits)}`;
}

export type Tone = "better" | "worse" | "mixed" | "same";

export interface Verdict {
  tone: Tone;
  headline: string;
  detail: string;
}

const cases = (n: number) => `${n} ${n === 1 ? "case" : "cases"}`;

/**
 * One honest sentence about the change. It counts what moved and does not say "improved": a pass rate that goes up
 * while a working case breaks is mixed, and the page says so.
 */
export function verdict(c: Comparison): Verdict {
  const noun = (n: number) => (c.kind === "faultlab" ? `${n} ${n === 1 ? "fault" : "faults"}` : cases(n));
  const net = c.fixed - c.broken;
  const netText = net === 0 ? "net zero" : `net ${net > 0 ? "+" : "−"}${Math.abs(net)}`;
  if (c.fixed === 0 && c.broken === 0) {
    return { tone: "same", headline: "Nothing changed", detail: `All ${noun(c.matched)} that both ran gave the same verdict.` };
  }
  if (c.broken === 0) {
    return { tone: "better", headline: `${noun(c.fixed)} fixed, none broken`, detail: "Nothing that worked before stopped working." };
  }
  if (c.fixed === 0) {
    return { tone: "worse", headline: `${noun(c.broken)} broken, none fixed`, detail: "Things that worked before stopped working, and nothing was gained." };
  }
  return {
    tone: "mixed",
    headline: `${noun(c.fixed)} fixed, ${noun(c.broken)} broken`,
    detail: `Some problems were solved and some working cases stopped working (${netText}). Look at which ones below.`,
  };
}

/** How many of the matched cases passed on each side. */
export function passCounts(c: Comparison): { before: number; after: number; total: number } {
  const matched = c.cases.filter((x) => x.change !== "only_baseline" && x.change !== "only_candidate");
  return {
    before: matched.filter((x) => x.baseline_passed).length,
    after: matched.filter((x) => x.candidate_passed).length,
    total: matched.length,
  };
}

export interface CostRow {
  label: string;
  before: string;
  after: string;
  change: string;
  /** Plain-language note shown under the label. */
  note?: string;
}

const dur = (ms: number | null) => (ms == null ? "–" : formatDuration(ms));

export function costRows(before: CostTotals, after: CostTotals): CostRow[] {
  const rows: CostRow[] = [
    { label: "Tool calls", before: String(before.tool_calls), after: String(after.tool_calls), change: delta(before.tool_calls, after.tool_calls) },
    { label: "Model calls", before: String(before.model_calls), after: String(after.model_calls), change: delta(before.model_calls, after.model_calls) },
    { label: "Retries", before: String(before.retries), after: String(after.retries), change: delta(before.retries, after.retries) },
    {
      label: "Median run time",
      before: dur(before.median_duration_ms),
      after: dur(after.median_duration_ms),
      change: before.median_duration_ms == null || after.median_duration_ms == null ? "–" : delta(before.median_duration_ms / 1000, after.median_duration_ms / 1000, 1) + (after.median_duration_ms === before.median_duration_ms ? "" : " s"),
      note: "The fair number: one slow case cannot move it.",
    },
    {
      label: "Total run time",
      before: dur(before.total_duration_ms),
      after: dur(after.total_duration_ms),
      change: delta(before.total_duration_ms / 1000, after.total_duration_ms / 1000, 1) + (after.total_duration_ms === before.total_duration_ms ? "" : " s"),
      note: "Includes any stall: one stuck model call can dominate it.",
    },
  ];
  if (before.input_tokens != null && after.input_tokens != null && before.output_tokens != null && after.output_tokens != null) {
    rows.push(
      { label: "Prompt tokens", before: String(before.input_tokens), after: String(after.input_tokens), change: delta(before.input_tokens, after.input_tokens) },
      { label: "Reply tokens", before: String(before.output_tokens), after: String(after.output_tokens), change: delta(before.output_tokens, after.output_tokens) },
    );
  }
  return rows;
}

/** Two runs of the same agent: the differences are run-to-run noise, not a change. */
export function sameAgent(c: Comparison): boolean {
  return c.baseline.variant === c.candidate.variant;
}
