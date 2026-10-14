import type {
  CheckResult, EvalCaseResult, EvalReport, FaultLabNote, LabRunSummary, RunEvaluation, RunFault, RunRecord, ScenarioInfo,
  SpanRecord, Suspect,
} from "../api/types";

export function span(over: Partial<SpanRecord> & Pick<SpanRecord, "span_id" | "name">): SpanRecord {
  return {
    run_id: "run-1",
    trace_id: "t".repeat(32),
    parent_span_id: null,
    span_type: "other",
    start_time_ns: 0,
    end_time_ns: 0,
    start_offset_ms: 0,
    duration_ms: 1,
    status: "unset",
    status_message: null,
    attributes: {},
    events: [],
    ...over,
  };
}

export function run(over: Partial<RunRecord> = {}): RunRecord {
  return {
    run_id: "run-aaaa1111",
    task: "Order 42 arrived damaged, please refund it.",
    model: "scripted:refund_happy_path",
    status: "ok",
    trace_id: "ab073c705c6644365dd6cf0818d63d87",
    started_at: new Date().toISOString(),
    duration_ms: 42,
    final_answer: "I issued a refund of $59.90 for order 42.",
    error: null,
    ...over,
  };
}

export const SCENARIOS: ScenarioInfo[] = [
  { name: "refund_happy_path", description: "Refund an eligible order.", example_task: "Order 42 arrived damaged, please refund it." },
  { name: "unknown_order", description: "Order id does not exist.", example_task: "Where is order 999?" },
];

/** A realistic happy-path trace: root agent span with model and tool children. */
export function happyPathSpans(): SpanRecord[] {
  return [
    span({ span_id: "root", name: "agent.run", span_type: "agent", start_offset_ms: 0, duration_ms: 22000,
      attributes: { "blackbox.agent.input": "Order 42 arrived damaged", "blackbox.agent.output": "Refund issued." } }),
    span({ span_id: "m1", parent_span_id: "root", name: "model.plan", span_type: "llm", start_offset_ms: 1, duration_ms: 12000,
      attributes: { "gen_ai.request.model": "qwen2.5:7b", "gen_ai.usage.input_tokens": 431, "gen_ai.usage.output_tokens": 22 } }),
    span({ span_id: "t1", parent_span_id: "root", name: "tool.lookup_order", span_type: "tool", start_offset_ms: 12001, duration_ms: 0.08,
      status: "ok",
      attributes: {
        "blackbox.tool.args": JSON.stringify({ order_id: 42 }),
        "blackbox.tool.output": JSON.stringify({ order_id: 42, customer_email: "[REDACTED]", shipping_address: "[REDACTED]", total: 59.9 }),
      } }),
    span({ span_id: "m2", parent_span_id: "root", name: "model.finalize", span_type: "llm", start_offset_ms: 12002, duration_ms: 9990 }),
  ];
}

export function check(over: Partial<CheckResult> & Pick<CheckResult, "metric">): CheckResult {
  return { passed: true, score: 1, reason: "ok", span_ids: [], details: {}, gating: false, ...over };
}

const ALL_PASS: CheckResult[] = [
  check({ metric: "task_completion", gating: true, reason: "outcome and answer match what was expected" }),
  check({ metric: "policy_compliance", gating: true, reason: "no policy violations" }),
  check({ metric: "tool_correctness", reason: "required calls made in order, nothing unexpected" }),
  check({ metric: "argument_correctness", reason: "arguments match" }),
  check({ metric: "step_efficiency", reason: "3 tool calls (optimal 3)" }),
  check({ metric: "trace_completeness", reason: "the trace is whole and consistent" }),
  check({ metric: "tool_output_contract", reason: "every successful tool call returned what its contract allows" }),
  check({ metric: "latency", passed: null, score: null, reason: "total 22212.0 ms" }),
];

export function withFailures(failures: Record<string, Partial<CheckResult>>): CheckResult[] {
  return ALL_PASS.map((c) => (failures[c.metric] ? { ...c, passed: false, score: 0, ...failures[c.metric] } : c));
}

export function caseResult(over: Partial<EvalCaseResult> = {}): EvalCaseResult {
  return {
    case_id: "N1", category: "normal", task: "Order 42 arrived damaged, please refund it.", run_id: "run-n1",
    run_status: "ok", passed: true, duration_ms: 12000, note: null, checks: ALL_PASS, ...over,
  };
}

export function evalReport(over: Partial<EvalReport> = {}): EvalReport {
  const cases = [
    caseResult({ case_id: "N1" }),
    caseResult({
      case_id: "N6", task: "Send order 45 to 5 Elm Street.", run_id: "run-n6", passed: false,
      checks: withFailures({
        policy_compliance: { reason: "update_shipping_address on order 45 without a successful lookup first", span_ids: ["t1"] },
        tool_correctness: { reason: "required call to lookup_order is missing or out of order", gating: false },
      }),
    }),
    caseResult({ case_id: "A1", category: "ambiguous", task: "I want a refund.", run_id: "run-a1" }),
  ];
  return {
    eval_id: "eval-bench", kind: "benchmark", model: "ollama:qwen2.5:7b", dataset_version: "golden-v2",
    dataset_hash: "abc123def456", seed: 0, started_at: new Date().toISOString(), finished_at: new Date().toISOString(),
    status: "done", n_cases: 3, n_passed: 2, cases,
    metrics: [
      { metric: "task_completion", gating: true, passed: 3, total: 3, mean_score: 1 },
      { metric: "policy_compliance", gating: true, passed: 2, total: 3, mean_score: 0.67 },
      { metric: "tool_correctness", gating: false, passed: 2, total: 3, mean_score: 0.67 },
      { metric: "argument_correctness", gating: false, passed: 3, total: 3, mean_score: 1 },
      { metric: "step_efficiency", gating: false, passed: 3, total: 3, mean_score: 1 },
      { metric: "trace_completeness", gating: false, passed: 3, total: 3, mean_score: 1 },
      { metric: "latency", gating: false, passed: 0, total: 0, mean_score: null },
    ],
    categories: [{ category: "normal", passed: 1, total: 2 }, { category: "ambiguous", passed: 1, total: 1 }],
    ...over,
  };
}

export function runEvaluation(over: Partial<RunEvaluation> = {}): RunEvaluation {
  return { run_id: "run-aaaa1111", eval_id: "eval-bench", case_id: "N1", stored: true, checks: ALL_PASS, suspects: [], ...over };
}

export function suspect(over: Partial<Suspect> = {}): Suspect {
  return { span_id: "t1", span_name: "tool.lookup_order", tier: 0, source: "tool output contract", reason: "lookup_order returned an error page", ...over };
}

export function runFault(over: Partial<RunFault> = {}): RunFault {
  return { kind: "malformed_output", tool: "lookup_order", occurrence: 1, description: "malformed_output on lookup_order call 1", origin_span_id: "t1", fired: true, ...over };
}

function labRun(over: Partial<LabRunSummary> = {}): LabRunSummary {
  return { run_id: "run-control", run_status: "ok", gating_passed: true, failed_checks: [], duration_ms: 3, tool_calls: 3, answer: "done", ...over };
}

export function faultLabNote(over: Partial<FaultLabNote> = {}): FaultLabNote {
  return {
    kind: "faultlab", fault: "malformed_output", title: "Malformed tool output",
    description: "The order lookup returns an error web page instead of an order.",
    injected: "malformed_output on lookup_order call 1", fired: true, origin_span_id: "t1", origin_span_name: "tool.lookup_order",
    suspects: [suspect(), suspect({ span_id: "t9", span_name: "tool.issue_refund", tier: 1, source: "policy compliance", reason: "refund not approved" })],
    rank: 1, hit_at_1: true, hit_at_3: true,
    control: labRun(),
    faulted: labRun({ run_id: "run-faulted", failed_checks: ["tool_output_contract"], duration_ms: 4 }),
    effect: "silent", ...over,
  };
}

export function faultLabCase(over: Partial<EvalCaseResult> = {}, note: Partial<FaultLabNote> = {}): EvalCaseResult {
  const n = faultLabNote(note);
  return {
    case_id: n.fault, category: "faultlab", task: "Order 42 arrived damaged, please refund it.", run_id: "run-faulted",
    run_status: "ok", passed: n.hit_at_1, duration_ms: 4, note: n, checks: [], ...over,
  };
}

export function faultLabReport(over: Partial<EvalReport> = {}): EvalReport {
  return {
    eval_id: "eval-lab", kind: "faultlab", model: "scripted:faultlab", dataset_version: "golden-v2", dataset_hash: "abc123def456",
    seed: null, started_at: new Date().toISOString(), finished_at: new Date().toISOString(), status: "done", n_cases: 2, n_passed: 1,
    cases: [
      faultLabCase(),
      faultLabCase({ case_id: "tool_timeout", run_id: "run-timeout" }, {
        fault: "tool_timeout", title: "Tool timeout", description: "The policy check does not answer in time.",
        injected: "tool_timeout on check_refund_policy call 1", effect: "run_failed", rank: 2, hit_at_1: false, hit_at_3: true,
        origin_span_id: "t5", origin_span_name: "tool.check_refund_policy",
        suspects: [suspect({ span_id: "t1", span_name: "tool.lookup_order", tier: 3, source: "error status", reason: "boom" }),
                   suspect({ span_id: "t5", span_name: "tool.check_refund_policy", tier: 3, source: "error status", reason: "timed out after 0.3s" })],
        faulted: labRun({ run_id: "run-timeout", run_status: "error", gating_passed: false, failed_checks: ["task_completion"], tool_calls: 2, duration_ms: 310 }),
      }),
    ],
    metrics: [], categories: [], ...over,
  };
}
