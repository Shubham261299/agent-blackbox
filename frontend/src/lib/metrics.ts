import type { EvalKind, EvalReport } from "../api/types";
import { plainWords } from "./plain";

export interface MetricInfo {
  label: string;
  /** One plain sentence on what the check looks at. */
  what: string;
}

export const METRICS: Record<string, MetricInfo> = {
  task_completion: {
    label: "Task completion",
    what: "The outcome matches what was expected (refunds, address changes), the answer says the right thing, and it does not claim something that never happened.",
  },
  policy_compliance: {
    label: "Policy compliance",
    what: "No refund without a prior policy check that approved it, nothing above the $100 limit, and no change before looking the order up.",
  },
  tool_correctness: {
    label: "Tool correctness",
    what: "The required tools were called in order, and no forbidden or unexpected tool was used.",
  },
  argument_correctness: {
    label: "Argument correctness",
    what: "The arguments of the expected tool calls are right (order id, amount). Redacted values cannot be checked.",
  },
  step_efficiency: {
    label: "Step efficiency",
    what: "The number of tool calls stays close to the minimum the task needs.",
  },
  trace_completeness: {
    label: "Trace completeness",
    what: "The recorded trace is whole and consistent: one root, every call has a span, errors are marked.",
  },
  tool_output_contract: {
    label: "Tool output contract",
    what: "Every successful tool call returned what its contract allows. Catches the silent failure, where a tool answers with garbage and nothing raises.",
  },
  latency: {
    label: "Latency",
    what: "How long the run and its parts took. Informational, not a pass or fail.",
  },
};

/** The metrics that produce a pass or fail, in display order. */
export const JUDGED_METRICS = [
  "task_completion",
  "policy_compliance",
  "tool_correctness",
  "argument_correctness",
  "step_efficiency",
  "trace_completeness",
  "tool_output_contract",
] as const;

/** The same checks in everyday words, for the recorded demo. */
export const PLAIN_METRICS: Record<string, MetricInfo> = {
  task_completion: {
    label: "Finished the job",
    what: "The agent did what the customer asked (for example, the refund really happened) and its answer says so truthfully.",
  },
  policy_compliance: {
    label: "Followed the rules",
    what: "No refund without a policy check, nothing above the $100 limit, and no change before looking the order up.",
  },
  tool_correctness: {
    label: "Used the right tools",
    what: "The agent used the tools the task needed, in a sensible order, and nothing it should not have.",
  },
  argument_correctness: {
    label: "Got the details right",
    what: "The details given to each tool, like the order number and the amount, were correct.",
  },
  step_efficiency: {
    label: "No wasted steps",
    what: "The agent did not take many more steps than the task needs.",
  },
  trace_completeness: {
    label: "Recording is complete",
    what: "The recording of the run has no gaps.",
  },
  tool_output_contract: {
    label: "Tools answered usably",
    what: "Every tool answered in a form the agent can use. This catches a tool that returns garbage without any error.",
  },
  latency: {
    label: "Speed",
    what: "How long the run and its steps took. Reported, not pass or fail.",
  },
};

export function metricLabel(metric: string): string {
  return (plainWords() ? PLAIN_METRICS : METRICS)[metric]?.label ?? metric.replaceAll("_", " ");
}

/** One sentence on what a check looks at, in the words of the current mode. */
export function metricWhat(metric: string): string | undefined {
  return (plainWords() ? PLAIN_METRICS : METRICS)[metric]?.what;
}

export const KIND_LABEL: Record<EvalKind, string> = {
  benchmark: "Benchmark",
  reference: "Reference run",
  validation: "Check validation",
  faultlab: "Failure lab",
};

export const PLAIN_KIND_LABEL: Record<EvalKind, string> = {
  benchmark: "Measured run",
  reference: "Sanity check",
  validation: "Checker test",
  faultlab: "Failure lab",
};

export function kindLabel(kind: EvalKind): string {
  return (plainWords() ? PLAIN_KIND_LABEL : KIND_LABEL)[kind];
}

/** What a viewer should and should not conclude from this kind of evaluation. */
export function kindNote(report: Pick<EvalReport, "kind" | "model" | "n_cases" | "seed">): string {
  if (plainWords()) return plainKindNote(report);
  switch (report.kind) {
    case "benchmark":
      return `Measured on ${report.model} with seed ${report.seed ?? 0}, one run per case (n=${report.n_cases}). One sample per case, so small differences are noise.`;
    case "reference":
      return "A scripted, correct run of every case. It shows the pipeline works end to end and says nothing about any model.";
    case "faultlab":
      return "Each fault was planted into the same refund task, next to an untouched control run. Trace analysis then ranked suspect spans from the trace alone, without being told what was planted. Located means its top suspect is the span the fault was planted in. Four faults on one task is a demonstration, not a benchmark.";
    case "validation":
      return "Known faults planted into runs. A row passes when the checks reacted exactly as expected: they caught the fault and flagged nothing else.";
  }
}

function plainKindNote(report: Pick<EvalReport, "kind" | "model" | "n_cases">): string {
  const model = report.model.slice(report.model.indexOf(":") + 1);
  switch (report.kind) {
    case "benchmark":
      return `One version of the agent, tried once on each of ${report.n_cases} test cases, on the AI model ${model}. With one try per case, small differences are just noise.`;
    case "reference":
      return "A scripted run where every answer is correct. It shows the whole pipeline works. It says nothing about any AI model.";
    case "faultlab":
      return "I planted each problem on purpose in the same refund task, next to a run with nothing planted. Then the analysis tried to say which step to look at, without being told what I planted. Four problems on one task is a demonstration, not a benchmark.";
    case "validation":
      return "I planted known problems in scripted runs. A row passes when the checks reacted exactly as expected: they caught the problem and flagged nothing else.";
  }
}

export function ratePercent(passed: number, total: number): number {
  return total > 0 ? Math.round((passed / total) * 100) : 0;
}
