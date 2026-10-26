import type { Comparison, EvalReport, EvalRunSummary, RunEvaluation, RunRecord, SpanRecord } from "../api/types";
import { variantLabel } from "../lib/compare";
import { formatDuration } from "../lib/timeScale";

/** The sentences the recorded demo says about a page before any table: what you are looking at, and what to notice. */

export const RUNS_LEAD =
  "Each row is one conversation between a customer and the AI agent. Failed runs are listed first. Open any run to see what the agent did, step by step.";

export const EVALS_LEAD =
  "Each row is a set of results: one version of the agent, tried on the same test cases and judged by the same rules. Open one to see the details, or pick two to compare them.";

const noun = (kind: string, n: number) => (kind === "faultlab" ? (n === 1 ? "planted problem" : "planted problems") : n === 1 ? "test case" : "test cases");

export function evalLead(report: Pick<EvalReport, "kind" | "n_cases" | "n_passed">): string {
  switch (report.kind) {
    case "benchmark":
      return `This is one version of the agent tried on ${report.n_cases} test cases. Each case is a customer request with a known right outcome. The big number counts the cases where the agent finished the job and followed the rules.`;
    case "reference":
      return "This is a scripted run where every answer is correct. It shows the whole pipeline works from start to finish. It says nothing about any AI model.";
    case "validation":
      return "This tests the checker itself. I planted known problems in scripted runs and asked whether the checks catch exactly the right ones and nothing else.";
    case "faultlab":
      return "This is the failure lab. I planted problems on purpose, one at a time, and asked whether the analysis points at the right step without being told what I planted.";
  }
}

export function compareLead(c: Comparison): string {
  const before = variantLabel(c.baseline.variant);
  const after = variantLabel(c.candidate.variant);
  const lab = c.kind === "faultlab";
  const head =
    c.baseline.variant === c.candidate.variant
      ? `Both sides are the same agent (${before}), so any difference below is just run-to-run noise.`
      : `I compared \u201c${after}\u201d with \u201c${before}\u201d on the same ${c.matched} ${noun(c.kind, c.matched)}.`;
  const fixed = lab ? "Fixed means a planted problem used to hurt the run and now does not." : "Fixed means a case used to fail and now passes.";
  const broken = lab ? "Broken means it went the other way." : "Broken means a case used to pass and now fails.";
  const passing = lab ? "" : " Passing means the agent finished the job and followed the rules.";
  return `${head} ${fixed} ${broken}${passing} A fix that breaks working cases is not free.`;
}

// ---- one run, step by step -----------------------------------------------------------------------------------

export interface Step {
  n: number;
  spanId: string;
  text: string;
  ms: number;
  failed: boolean;
  retries: number;
  /** What the failed step reported, for someone who wants the detail. */
  detail?: string;
}

export interface RunStory {
  steps: Step[];
  sentence: string;
  finished: boolean | null;
  rules: boolean | null;
  /** The step to look at first, when the analysis names one. */
  where?: string;
}

const TOOL_TEXT: Record<string, (order?: string) => string> = {
  lookup_order: (o) => (o ? `Looked up order ${o}` : "Looked up the order"),
  check_refund_policy: (o) => (o ? `Checked the refund policy for order ${o}` : "Checked the refund policy"),
  issue_refund: (o) => (o ? `Issued a refund on order ${o}` : "Issued a refund"),
  update_shipping_address: (o) => (o ? `Changed the shipping address on order ${o}` : "Changed the shipping address"),
};

function orderOf(span: SpanRecord): string | undefined {
  const raw = span.attributes["blackbox.tool.args"];
  if (typeof raw !== "string") return undefined;
  try {
    const id = (JSON.parse(raw) as { order_id?: unknown }).order_id;
    return typeof id === "number" || typeof id === "string" ? String(id) : undefined;
  } catch {
    return undefined;
  }
}

/** One span in a sentence a customer-support manager could read. */
export function stepText(span: SpanRecord): string {
  if (span.name === "model.plan") return "Asked the AI model what to do";
  if (span.name === "model.call") return "Asked the AI model what to do next";
  if (span.name === "model.finalize") return "Asked the AI model to write the reply";
  if (span.name.startsWith("tool.")) {
    const tool = span.name.slice("tool.".length);
    const make = TOOL_TEXT[tool];
    return make ? make(orderOf(span)) : `Used the “${tool.replaceAll("_", " ")}” tool`;
  }
  return span.name;
}

/** The run told as a list of steps, with what the checks said about it. Pure: spans, run and evaluation in, text out. */
export function runStory(run: Pick<RunRecord, "status">, spans: SpanRecord[], evaluation?: RunEvaluation): RunStory {
  const steps: Step[] = spans
    .filter((s) => s.parent_span_id !== null)
    .map((s, i) => ({
      n: i + 1,
      spanId: s.span_id,
      text: stepText(s),
      ms: s.duration_ms,
      failed: s.status === "error",
      retries: Number(s.attributes["blackbox.agent.retry_count"] ?? 0) || 0,
      detail: s.status === "error" ? (s.status_message ?? undefined) : undefined,
    }));

  const passed = (metric: string): boolean | null => {
    const check = evaluation?.checks.find((c) => c.metric === metric);
    return check ? check.passed : null;
  };
  const finished = passed("task_completion");
  const rules = passed("policy_compliance");
  const failedStep = steps.find((s) => s.failed);
  const count = `${steps.length} ${steps.length === 1 ? "step" : "steps"}`;

  let sentence: string;
  if (run.status === "error") {
    sentence = `The run stopped with an error after ${count}.${failedStep ? ` Step ${failedStep.n} is where it failed.` : ""}`;
  } else if (finished === false) {
    sentence = `The agent took ${count} and gave an answer, but it did not finish the job.`;
  } else if (rules === false) {
    sentence = `The agent took ${count} and finished, but it broke a rule on the way.`;
  } else if (finished === true) {
    sentence = `The agent took ${count} and finished the job.`;
  } else {
    sentence = `The agent took ${count} and gave an answer.`;
  }

  const top = evaluation?.suspects[0];
  const topStep = top ? steps.find((s) => s.spanId === top.span_id) : undefined;
  const where = top ? (topStep ? `Step ${topStep.n}: ${topStep.text}` : "The run as a whole") : undefined;
  return { steps, sentence, finished, rules, where };
}

export const stepTime = (ms: number) => formatDuration(ms);

/** A span's name for a reader who has not met spans: what the step was, without the order number. */
export function plainStepName(spanName: string): string {
  if (spanName === "agent.run") return "The run as a whole";
  if (spanName.startsWith("model.")) return "Asked the AI model";
  if (spanName.startsWith("tool.")) {
    const tool = spanName.slice("tool.".length);
    return TOOL_TEXT[tool] ? TOOL_TEXT[tool]() : `Used the \u201c${tool.replaceAll("_", " ")}\u201d tool`;
  }
  return spanName;
}

const SOURCE_TEXT: Record<string, string> = {
  "error status": "it reported an error",
  "tool output contract": "its answer could not be used",
  "policy compliance": "a rule was broken",
  "task completion": "the job was not finished",
  retried: "it needed retries",
};

/** Why the analysis suggested a step, in everyday words. An unknown reason is shown as it is. */
export function plainSource(source: string): string {
  return SOURCE_TEXT[source] ?? source;
}

// ---- the run list --------------------------------------------------------------------------------------------

/**
 * Failed runs first, then the runs of the real model, then the scripted examples, each group keeping the order it came
 * in. A visitor sees the interesting runs at the top instead of 24 scripted ones.
 */
export function runOrder(runs: RunRecord[]): RunRecord[] {
  const rank = (r: RunRecord) => (r.status === "error" ? 0 : r.model.startsWith("ollama:") ? 1 : 2);
  return [...runs].sort((a, b) => rank(a) - rank(b)); // sorting is stable, so each group keeps its order
}

/** How the evaluations table names a model in everyday words. */
export function plainModel(model: string): string {
  return model.startsWith("scripted:") ? "Scripted (no AI model)" : model.slice(model.indexOf(":") + 1);
}

export function plainDataset(e: Pick<EvalRunSummary, "dataset_version" | "n_cases">): string {
  return `${e.n_cases} test cases`;
}
