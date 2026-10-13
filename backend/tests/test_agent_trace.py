import json

from blackbox.llm.base import ModelResponse, ToolRequest
from blackbox.llm.scripted import ScriptedModel, scripted_model

HAPPY_NAMES = [
    "agent.run",
    "model.plan", "tool.lookup_order",
    "model.call", "tool.check_refund_policy",
    "model.call", "tool.issue_refund",
    "model.finalize",
]


def spans_by_name(store, run_id="run-test"):
    return {s.name: s for s in reversed(store.get_spans(run_id))}


def test_happy_path_span_tree(run_agent, store):
    result = run_agent(scripted_model("refund_happy_path"))
    assert result.status == "ok" and "$59.90" in result.final_answer and result.steps == 4

    spans = store.get_spans("run-test")
    assert [s.name for s in spans] == HAPPY_NAMES

    root, children = spans[0], spans[1:]
    assert root.parent_span_id is None and root.status == "unset"
    assert all(c.parent_span_id == root.span_id for c in children)  # flat: model/tool spans are children of the run
    assert {s.trace_id for s in spans} == {result.trace_id}
    assert all(s.run_id == "run-test" and s.duration_ms > 0 for s in spans)
    assert [s.span_type for s in spans] == ["agent", "llm", "tool", "llm", "tool", "llm", "tool", "llm"]
    assert all(c.start_time_ns >= root.start_time_ns and c.end_time_ns <= root.end_time_ns for c in children)


def test_span_attributes(run_agent, store):
    run_agent(scripted_model("refund_happy_path"))
    s = spans_by_name(store)
    assert json.loads(s["tool.lookup_order"].attributes["blackbox.tool.args"]) == {"order_id": 42}
    assert s["tool.issue_refund"].attributes["gen_ai.operation.name"] == "execute_tool"
    assert s["tool.issue_refund"].status == "ok"
    assert s["agent.run"].attributes["gen_ai.operation.name"] == "invoke_agent"
    assert s["agent.run"].attributes["blackbox.agent.steps"] == 4
    assert "$59.90" in s["agent.run"].attributes["blackbox.agent.output"]
    plan = s["model.plan"].attributes
    assert plan["gen_ai.provider.name"] == "scripted" and plan["blackbox.agent.step"] == 1
    # scripted model reports no token counts, so none must be invented
    assert "gen_ai.usage.input_tokens" not in plan


def test_token_counts_recorded_when_model_reports_them(run_agent, store):
    model = ScriptedModel([ModelResponse(content="done", input_tokens=120, output_tokens=7)])
    run_agent(model)
    attrs = spans_by_name(store)["model.finalize"].attributes
    assert attrs["gen_ai.usage.input_tokens"] == 120 and attrs["gen_ai.usage.output_tokens"] == 7


def test_no_raw_pii_reaches_stored_spans(run_agent, store):
    run_agent(scripted_model("refund_happy_path"))
    dump = json.dumps([s.model_dump() for s in store.get_spans("run-test")])
    for leaked in ("ava.martin@example.com", "Birch Lane"):
        assert leaked not in dump
    lookup = spans_by_name(store)["tool.lookup_order"]
    assert json.loads(lookup.attributes["blackbox.tool.output"])["customer_email"] == "[REDACTED]"


def test_expected_tool_failure_is_recorded_and_agent_recovers(run_agent, store):
    result = run_agent(scripted_model("unknown_order"))
    assert result.status == "ok"  # the agent handled the error and answered
    s = spans_by_name(store)
    failed = s["tool.lookup_order"]
    assert failed.status == "error" and "not found" in failed.status_message
    assert [e["name"] for e in failed.events] == ["exception"]
    assert s["agent.run"].status == "unset"
    assert json.loads(failed.attributes["blackbox.tool.output"]) == {"error": "order 999 not found"}


def test_unknown_tool_and_bad_arguments_fail_the_tool_span_only(run_agent, store):
    model = ScriptedModel([
        ModelResponse(tool_calls=[ToolRequest("delete_everything", {})]),
        ModelResponse(tool_calls=[ToolRequest("lookup_order", {})]),  # missing required order_id
        ModelResponse(content="giving up"),
    ])
    result = run_agent(model)
    assert result.status == "ok"
    tools = [s for s in store.get_spans("run-test") if s.span_type == "tool"]
    assert [t.status for t in tools] == ["error", "error"]
    assert "unknown tool" in tools[0].status_message
    assert "invalid arguments" in tools[1].status_message


def test_model_failure_marks_model_and_root_spans_and_does_not_fall_back(run_agent, store):
    result = run_agent(ScriptedModel([]))  # first call raises ScriptExhausted
    assert result.status == "error" and "ScriptExhausted" in result.error and result.trace_id
    s = spans_by_name(store)
    assert s["model.call"].status == "error" and s["model.call"].events[0]["name"] == "exception"
    assert s["agent.run"].status == "error"
    assert s["agent.run"].span_id == s["model.call"].parent_span_id


def test_max_steps_exceeded(run_agent, store):
    looping = ScriptedModel([ModelResponse(tool_calls=[ToolRequest("lookup_order", {"order_id": 42})])] * 5)
    result = run_agent(looping, max_steps=2)
    assert result.status == "error" and "max steps" in result.error and result.steps == 2
    spans = store.get_spans("run-test")
    assert sum(s.name.startswith("model.") for s in spans) == 2
    assert spans[0].status == "error" and "max steps" in spans[0].status_message
