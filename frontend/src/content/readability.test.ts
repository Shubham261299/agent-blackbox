/**
 * The words the plain demo says itself (not the recorded data) must be easy to read, as a number: a short average
 * sentence, no long sentence anywhere, and no jargon. This is the corpus; a new sentence added to a plain page belongs here.
 */
import { afterAll, afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Comparison, EvalRunSummary, DemoManifest, RunEvaluation, RunRecord, SpanRecord } from "../api/types";
import { PLAIN_VARIANT_INFO } from "../lib/compare";
import { PLAIN_KIND_LABEL, PLAIN_METRICS, kindNote } from "../lib/metrics";
import { effectLabel, effectText, verdictText } from "../lib/notes";
import { setPlainWords } from "../lib/plain";
import { BANNED_WORDS, jargonIn, longestSentence, readingGrade, words } from "../lib/readability";
import { tourStops } from "../lib/tour";
import { faultLabNote } from "../test/factories";
import { demoJson } from "../test/realDemo";
import { EVALS_LEAD, RUNS_LEAD, compareLead, evalLead, plainFault, plainReason, plainRefusal, plainSource, plainStepName, runStory } from "./plain";
import { buildStory, storyText } from "./story";

beforeEach(() => setPlainWords(true));
afterEach(() => setPlainWords(false));
afterAll(() => setPlainWords(false));

// Measured when written: about grade 4 overall (1,800 words in 47 blocks), no block above 9. The bounds leave room for
// new sentences but not for a drift into the technical wording the old pages used.
const MAX_GRADE_OVERALL = 6;
const MAX_GRADE_ANY_BLOCK = 10;
const MAX_WORDS_IN_A_SENTENCE = 30;

function corpus(): Record<string, string> {
  const manifest = demoJson<DemoManifest>("manifest.json");
  const evals = demoJson<EvalRunSummary[]>("evals.json");
  const index = demoJson<{ ok: Record<string, string> }>("comparisons/index.json").ok;
  const comparison = (pair?: [string, string]) => (pair ? demoJson<Comparison>(`comparisons/${index[`${pair[0]}|${pair[1]}`]}`) : undefined);
  const lab = comparison(manifest.tour.fixed);
  const bench = comparison(manifest.tour.regressed);
  const second = comparison(manifest.tour.second_attempt);
  const story = buildStory({ manifest, evals, lab, bench, second });
  const stops = tourStops(manifest.tour, lab, bench);

  const runs = demoJson<RunRecord[]>("runs.json");
  const failed = runs.find((r) => r.run_id === manifest.tour.failed_run) as RunRecord;
  const spans = demoJson<SpanRecord[]>(`spans/${failed.run_id}.json`);
  const evaluation = demoJson<RunEvaluation>(`run-evaluations/${failed.run_id}.json`);
  const ok = runs.find((r) => r.status === "ok" && r.model.startsWith("ollama:")) as RunRecord;
  const okStory = runStory(ok, demoJson<SpanRecord[]>(`spans/${ok.run_id}.json`), demoJson<RunEvaluation>(`run-evaluations/${ok.run_id}.json`));
  const failedStory = runStory(failed, spans, evaluation);

  const blocks: Record<string, string> = {
    "front page": storyText(story).map((t) => (/[.!?]$/.test(t) ? t : `${t}.`)).join(" "), // headings and labels count as sentences
    "tour stops": stops.map((s) => `${s.title}. ${s.text} ${s.notice}`).join(" "),
    "run list lead": RUNS_LEAD,
    "results list lead": EVALS_LEAD,
    "compare lead": [bench, lab, second].flatMap((c) => (c ? [compareLead(c)] : [])).join(" "),
    "run story": `${failedStory.sentence} ${okStory.sentence} ${failedStory.where ?? ""}`,
  };
  for (const kind of ["benchmark", "reference", "validation", "faultlab"] as const) {
    blocks[`results lead: ${kind}`] = evalLead({ kind, n_cases: 24, n_passed: 19 });
    blocks[`note: ${kind}`] = kindNote({ kind, model: "ollama:qwen2.5:7b", n_cases: 24, seed: 0 });
    blocks[`name: ${kind}`] = PLAIN_KIND_LABEL[kind];
  }
  for (const [name, m] of Object.entries(PLAIN_METRICS)) blocks[`check: ${name}`] = `${m.label}. ${m.what}`;
  for (const [name, v] of Object.entries(PLAIN_VARIANT_INFO)) blocks[`agent: ${name}`] = `${v.label}. ${v.what}`;
  for (const effect of ["run_failed", "gating_failed", "silent", "no_effect"] as const) blocks[`effect: ${effect}`] = `${effectLabel(effect)}. ${effectText(effect)}`;
  for (const [rank, fired] of [[1, true], [3, true], [null, true], [null, false]] as const) blocks[`finding: ${rank}/${fired}`] = verdictText(faultLabNote({ rank, fired, hit_at_1: rank === 1 }));
  for (const fault of ["tool_timeout", "malformed_output", "wrong_tool", "model_error"]) {
    const f = plainFault(fault, { title: "x", description: "x" });
    blocks[`planted: ${fault}`] = `${f.title}. ${f.description}`;
  }
  blocks["reasons"] = [
    "lookup_order returned data that breaks its contract: expected an object",
    "ToolTimeoutError: check_refund_policy timed out after 0.3s",
    "ModelUnavailableError: model backend unavailable: connection refused",
    "update_shipping_address on order 42 without a successful lookup first",
  ].map(plainReason).join(" ");
  blocks["refusals"] = [
    "An evaluation cannot be compared with itself.",
    "They ran different cases (a b against c d), so the difference could come from the test.",
    "They used different models (a and b).",
    "These are different kinds of evaluation (benchmark and faultlab).",
    "eval-1 is a validation evaluation: it checks the checks, not an agent, so there is nothing to compare.",
  ].map(plainRefusal).join(" ");
  blocks["suggestions"] = ["error status", "tool output contract", "policy compliance", "task completion", "retried"].map(plainSource).concat(["tool.lookup_order", "model.plan"].map(plainStepName)).join(". ");
  return blocks;
}

describe("the demo's own words are easy to read", () => {
  it("has no jargon anywhere in the corpus", () => {
    const leaks = Object.entries(corpus()).flatMap(([name, text]) => jargonIn(text, BANNED_WORDS).map((w) => `${name}: ${w}`));
    expect(leaks).toEqual([]);
  });

  it("averages at or below grade 6 over everything", () => {
    const all = Object.values(corpus()).join(" ");
    expect(words(all).length).toBeGreaterThan(1500); // it really is the whole corpus
    expect(readingGrade(all)).toBeLessThanOrEqual(MAX_GRADE_OVERALL);
  });

  it("keeps every block of real text at or below grade 10 (a short block swings, so the bound is looser)", () => {
    const hard = Object.entries(corpus())
      .filter(([, text]) => words(text).length >= 12)
      .map(([name, text]) => [name, readingGrade(text)] as const)
      .filter(([, grade]) => grade > MAX_GRADE_ANY_BLOCK);
    expect(hard).toEqual([]);
  });

  it(`has no sentence longer than ${MAX_WORDS_IN_A_SENTENCE} words`, () => {
    const long = Object.entries(corpus()).flatMap(([name, text]) => {
      const { words: n, sentence } = longestSentence(text);
      return n > MAX_WORDS_IN_A_SENTENCE ? [`${name}: ${n} words: ${sentence}`] : [];
    });
    expect(long).toEqual([]);
  });

  it("really measures: the old technical wording is caught by the jargon list, and a clumsy sentence by the length bound", () => {
    const old =
      "Each fault was planted into the same refund task, next to an untouched control run. Trace analysis then ranked suspect spans from the trace alone, without being told what was planted. Located means its top suspect is the span the fault was planted in. The recorded trace is whole and consistent: one root, every call has a span, errors are marked.";
    expect(jargonIn(old, BANNED_WORDS).length).toBeGreaterThan(2);
    const clumsy = "The agent that was given the rewritten set of instructions that tell it to look every order up first and to ask the customer instead of guessing when something is missing did worse than the original one did.";
    expect(longestSentence(clumsy).words).toBeGreaterThan(MAX_WORDS_IN_A_SENTENCE);
    expect(readingGrade(Array(40).fill("Notwithstanding unprecedented organisational interdependencies, institutional accountability necessitates.").join(" "))).toBeGreaterThan(MAX_GRADE_OVERALL);
  });
});
