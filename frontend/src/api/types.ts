// Mirrors backend/blackbox/models.py. Keep the two in sync.

export type RunStatus = "running" | "ok" | "error";
export type SpanStatus = "unset" | "ok" | "error";
export type SpanType = "agent" | "llm" | "tool" | "other";

export interface RunRecord {
  run_id: string;
  task: string;
  model: string;
  status: RunStatus;
  trace_id: string | null;
  started_at: string;
  duration_ms: number | null;
  final_answer: string | null;
  error: string | null;
}

export interface SpanEvent {
  name: string;
  timestamp_ns: number;
  attributes: Record<string, unknown>;
}

export interface SpanRecord {
  span_id: string;
  run_id: string;
  trace_id: string;
  parent_span_id: string | null;
  name: string;
  span_type: SpanType;
  start_time_ns: number;
  end_time_ns: number;
  start_offset_ms: number;
  duration_ms: number;
  status: SpanStatus;
  status_message: string | null;
  attributes: Record<string, unknown>;
  events: SpanEvent[];
}

export interface CheckResult {
  metric: string;
  /** null = informational (latency), not a pass/fail question */
  passed: boolean | null;
  score: number | null;
  reason: string;
  span_ids: string[];
  details: Record<string, unknown>;
  gating: boolean;
}

export type EvalKind = "benchmark" | "reference" | "validation" | "faultlab";

export interface EvalRunSummary {
  eval_id: string;
  kind: EvalKind;
  model: string;
  dataset_version: string;
  dataset_hash: string;
  seed: number | null;
  started_at: string;
  finished_at: string | null;
  status: "running" | "done" | "error";
  n_cases: number;
  n_passed: number;
}

export interface Suspect {
  span_id: string;
  span_name: string;
  /** 0 contract violation, 1 failed gating check, 2 failed reported check, 3 error status */
  tier: number;
  source: string;
  reason: string;
}

/** Ground truth for a failure-lab run: what was planted and where. Kept outside the trace on purpose. */
export interface RunFault {
  kind: string;
  tool: string | null;
  occurrence: number;
  description: string;
  origin_span_id: string | null;
  fired: boolean;
}

export interface ValidationNote {
  kind?: undefined;
  fault?: string;
  description?: string;
  expected_fail?: string[];
  actual_fail?: string[];
  matched?: boolean;
}

export interface LabRunSummary {
  run_id: string;
  run_status: RunStatus;
  gating_passed: boolean;
  failed_checks: string[];
  duration_ms: number | null;
  tool_calls: number;
  answer: string | null;
}

export type LabEffect = "run_failed" | "gating_failed" | "silent" | "no_effect";

export interface FaultLabNote {
  kind: "faultlab";
  fault: string;
  title: string;
  description: string;
  injected: string;
  fired: boolean;
  origin_span_id: string | null;
  origin_span_name: string | null;
  suspects: Suspect[];
  rank: number | null;
  hit_at_1: boolean;
  hit_at_3: boolean;
  control: LabRunSummary;
  faulted: LabRunSummary;
  effect: LabEffect;
}

export interface EvalCaseResult {
  case_id: string;
  category: string;
  task: string;
  run_id: string;
  run_status: RunStatus;
  passed: boolean;
  duration_ms: number | null;
  note: ValidationNote | FaultLabNote | null;
  checks: CheckResult[];
}

export interface MetricSummary {
  metric: string;
  gating: boolean;
  passed: number;
  total: number;
  mean_score: number | null;
}

export interface CategorySummary {
  category: string;
  passed: number;
  total: number;
}

export interface EvalReport extends EvalRunSummary {
  cases: EvalCaseResult[];
  metrics: MetricSummary[];
  categories: CategorySummary[];
}

export interface RunEvaluation {
  run_id: string;
  eval_id: string | null;
  case_id: string | null;
  stored: boolean;
  checks: CheckResult[];
  suspects: Suspect[];
}

export interface ScenarioInfo {
  name: string;
  description: string;
  example_task: string;
}

export interface RunRequest {
  task: string;
  model: "scripted" | "ollama";
  scenario?: string | null;
}
