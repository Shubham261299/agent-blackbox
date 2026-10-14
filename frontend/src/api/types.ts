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

export type EvalKind = "benchmark" | "reference" | "validation";

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

export interface EvalCaseResult {
  case_id: string;
  category: string;
  task: string;
  run_id: string;
  run_status: RunStatus;
  passed: boolean;
  duration_ms: number | null;
  note: {
    fault?: string;
    description?: string;
    expected_fail?: string[];
    actual_fail?: string[];
    matched?: boolean;
  } | null;
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
