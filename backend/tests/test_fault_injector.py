import json
import time

import pytest

from blackbox.agent.loop import AgentRunner
from blackbox.agent.tools import OrderDesk
from blackbox.faults.injector import (
    HTML_ERROR_PAGE,
    FaultInjector,
    FaultSpec,
    ModelUnavailableError,
    ToolTimeoutError,
)
from blackbox.llm.scripted import ScriptedModel
from blackbox.llm.base import ModelResponse, ToolRequest
from blackbox.evals.cases import load_dataset
from blackbox.evals.scripts import reference_script

N1 = load_dataset().case("N1")


def run(telemetry, injector, store, run_id="run-x"):
    model, tools = ScriptedModel(reference_script(N1), name="ref"), OrderDesk().registry()
    tools, model = injector.wrap_tools(tools), injector.wrap_model(model)
    result = AgentRunner(model, tools, telemetry.tracer(), 8).run(run_id, N1.task)
    telemetry.flush()
    return result, {s.span_id: s for s in store.get_spans(run_id)}


def test_tool_timeout_takes_real_time_ends_the_run_and_marks_the_tool_span(telemetry, store):
    spec = FaultSpec("tool_timeout", tool="check_refund_policy", params={"delay_s": 0.15})
    injector = FaultInjector([spec])
    started = time.perf_counter()
    result, spans = run(telemetry, injector, store)
    assert time.perf_counter() - started >= 0.15

    assert result.status == "error" and "ToolTimeoutError" in result.error
    (fired,) = injector.fired
    origin = spans[fired.origin_span_id]
    assert origin.name == "tool.check_refund_policy" and origin.status == "error"
    assert origin.duration_ms >= 150  # the wait is real time on the span
    assert [e["name"] for e in origin.events] == ["exception"]
    root = next(s for s in spans.values() if s.parent_span_id is None)
    assert root.status == "error"


def test_the_timeout_is_not_a_recoverable_tool_error(telemetry, store):
    injector = FaultInjector([FaultSpec("tool_timeout", tool="lookup_order", params={"delay_s": 0.01})])
    result, spans = run(telemetry, injector, store)
    assert result.status == "error"  # baseline behaviour on purpose: Day 5 adds the handling
    assert sum(s.span_type == "tool" for s in spans.values()) == 1  # nothing ran after it


def test_malformed_output_succeeds_as_far_as_the_trace_is_concerned(telemetry, store):
    injector = FaultInjector([FaultSpec("malformed_output", tool="lookup_order")])
    result, spans = run(telemetry, injector, store)
    (fired,) = injector.fired
    origin = spans[fired.origin_span_id]
    assert origin.name == "tool.lookup_order" and origin.status == "ok"  # no error anywhere: that is the point
    assert json.loads(origin.attributes["blackbox.tool.output"]) == HTML_ERROR_PAGE
    assert result.status == "ok"  # the scripted agent carries on regardless


@pytest.mark.parametrize("mode, check", [
    ("html", lambda out: isinstance(out, str)),
    ("missing_fields", lambda out: out == {}),
    ("wrong_types", lambda out: isinstance(out, dict) and out["total"] == "N/A"),
])
def test_malformed_modes(mode, check, telemetry, store):
    injector = FaultInjector([FaultSpec("malformed_output", tool="lookup_order", params={"mode": mode})])
    _, spans = run(telemetry, injector, store)
    origin = spans[injector.fired[0].origin_span_id]
    assert check(json.loads(origin.attributes["blackbox.tool.output"]))


def test_wrong_tool_swaps_the_models_first_call_and_the_origin_is_the_tool_span_that_ran(telemetry, store):
    spec = FaultSpec("wrong_tool", params={"to_tool": "update_shipping_address", "args": {"order_id": 42, "new_address": "1 Fault St"}})
    injector = FaultInjector([spec])
    result, spans = run(telemetry, injector, store)
    (fired,) = injector.fired
    origin = spans[fired.origin_span_id]
    assert origin.name == "tool.update_shipping_address"  # not the model span that chose it
    tool_names = [s.name for s in sorted(spans.values(), key=lambda s: s.start_offset_ms) if s.span_type == "tool"]
    assert tool_names[0] == "tool.update_shipping_address" and "tool.lookup_order" not in tool_names
    assert result.status == "ok"  # order 42 is delivered, so the address change fails as an expected tool error
    assert origin.status == "error"


def test_model_error_raises_on_the_chosen_call_and_marks_that_model_span(telemetry, store):
    injector = FaultInjector([FaultSpec("model_error", occurrence=2)])
    result, spans = run(telemetry, injector, store)
    (fired,) = injector.fired
    origin = spans[fired.origin_span_id]
    assert origin.span_type == "llm" and origin.status == "error"
    assert result.status == "error" and "ModelUnavailableError" in result.error
    assert sum(s.span_type == "tool" for s in spans.values()) == 1  # the lookup ran before the failure


def _visible_text(span) -> str:
    """Everything a trace reader sees on a span except stack frames, which name the code that raised."""
    events = [{k: v for k, v in e["attributes"].items() if k != "exception.stacktrace"} for e in span.events]
    return json.dumps([span.name, span.status_message, span.attributes, events]).lower()


def test_what_the_trace_says_does_not_reveal_that_a_fault_was_planted(telemetry, store):
    injector = FaultInjector([FaultSpec("tool_timeout", tool="check_refund_policy", params={"delay_s": 0.01}),
                              FaultSpec("model_error", occurrence=9)])
    _, spans = run(telemetry, injector, store)
    text = " ".join(_visible_text(s) for s in spans.values())
    assert "inject" not in text and "fault" not in text  # the exception type is blackbox.agent.errors.ToolTimeoutError
    (event,) = next(s for s in spans.values() if s.name == "tool.check_refund_policy").events
    assert event["attributes"]["exception.type"] == "blackbox.agent.errors.ToolTimeoutError"


def test_model_failure_message_reads_like_a_real_outage(telemetry, store):
    injector = FaultInjector([FaultSpec("model_error", occurrence=1)])
    _, spans = run(telemetry, injector, store)
    text = " ".join(_visible_text(s) for s in spans.values())
    assert "connection refused" in text and "inject" not in text


def test_a_fault_that_never_fires_is_reported_as_not_fired(telemetry, store):
    injector = FaultInjector([FaultSpec("tool_timeout", tool="issue_refund", occurrence=5)])
    run(telemetry, injector, store)
    assert injector.fired == [] and injector.faults[0].origin_span_id is None


def test_wrapping_keeps_argument_validation_working(telemetry, store):
    from blackbox.llm.base import ModelResponse as R
    model = ScriptedModel([R(tool_calls=[ToolRequest("lookup_order", {})]), R(content="done")], name="m")
    injector = FaultInjector([])
    tools, model = injector.wrap_tools(OrderDesk().registry()), injector.wrap_model(model)
    AgentRunner(model, tools, telemetry.tracer(), 4).run("run-args", "x")
    telemetry.flush()
    (tool,) = [s for s in store.get_spans("run-args") if s.span_type == "tool"]
    assert tool.status == "error" and "invalid arguments" in tool.status_message  # still a clean ToolError


def test_the_model_wrapper_looks_like_the_model_it_wraps():
    inner = ScriptedModel([ModelResponse(content="x")], name="inner-name")
    wrapped = FaultInjector([]).wrap_model(inner)
    assert (wrapped.provider, wrapped.name) == ("scripted", "inner-name")


def test_fault_spec_description_is_readable():
    assert FaultSpec("tool_timeout", tool="lookup_order", occurrence=2).describe() == "tool_timeout on lookup_order call 2"
    assert FaultSpec("model_error", occurrence=3).describe() == "model_error on model call 3"
    with pytest.raises(ToolTimeoutError):
        raise ToolTimeoutError("x")
    with pytest.raises(ModelUnavailableError):
        raise ModelUnavailableError("x")
