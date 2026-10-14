import type { EvalKind, EvalReport } from "../api/types";

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
  latency: {
    label: "Latency",
    what: "How long the run and its parts took. Informational, not a pass or fail.",
  },
};

/** The six metrics that produce a pass or fail, in display order. */
export const JUDGED_METRICS = [
  "task_completion",
  "policy_compliance",
  "tool_correctness",
  "argument_correctness",
  "step_efficiency",
  "trace_completeness",
] as const;

export function metricLabel(metric: string): string {
  return METRICS[metric]?.label ?? metric.replaceAll("_", " ");
}

export const KIND_LABEL: Record<EvalKind, string> = {
  benchmark: "Benchmark",
  reference: "Reference run",
  validation: "Check validation",
};

/** What a viewer should and should not conclude from this kind of evaluation. */
export function kindNote(report: Pick<EvalReport, "kind" | "model" | "n_cases" | "seed">): string {
  switch (report.kind) {
    case "benchmark":
      return `Measured on ${report.model} with seed ${report.seed ?? 0}, one run per case (n=${report.n_cases}). One sample per case, so small differences are noise.`;
    case "reference":
      return "A scripted, correct run of every case. It shows the pipeline works end to end and says nothing about any model.";
    case "validation":
      return "Known faults planted into runs. A row passes when the checks reacted exactly as expected: they caught the fault and flagged nothing else.";
  }
}

export function ratePercent(passed: number, total: number): number {
  return total > 0 ? Math.round((passed / total) * 100) : 0;
}
