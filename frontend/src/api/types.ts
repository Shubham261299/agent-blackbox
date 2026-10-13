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
