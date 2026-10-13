import type { RunRecord, ScenarioInfo, SpanRecord } from "../api/types";

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
