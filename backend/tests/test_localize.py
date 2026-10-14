import dataclasses

import pytest

from blackbox.evals.localize import locate
from blackbox.evals.trajectory import Trajectory
from blackbox.models import CheckResult, SpanRecord


def span(span_id, name, *, parent="root", offset=0.0, status="unset", message=None, kind="tool", attrs=None, events=None):
    return SpanRecord(span_id=span_id, run_id="r", trace_id="t", parent_span_id=parent, name=name, span_type=kind,
                      start_time_ns=0, end_time_ns=1, start_offset_ms=offset, duration_ms=1.0, status=status,
                      status_message=message, attributes=attrs or {}, events=events or [])


def traj(*spans):
    return Trajectory(run_id="r", task="t", run_status="ok", run_error=None, final_answer="", root=None,
                      tool_calls=[], model_calls=[], spans=list(spans))


def check(metric, span_ids, *, gating=False, passed=False, reason="why"):
    return CheckResult(metric=metric, passed=passed, reason=reason, span_ids=span_ids, gating=gating)


ROOT = span("root", "agent.run", parent=None, kind="agent")


def test_nothing_to_suspect_when_nothing_failed():
    assert locate(traj(ROOT, span("a", "tool.a", offset=1)), [check("policy_compliance", [], gating=True, passed=True)]) == []


def test_error_status_is_a_suspect_and_the_run_span_is_a_consequence():
    t = traj(span("root", "agent.run", parent=None, kind="agent", status="error", message="boom"),
             span("a", "tool.a", offset=1, status="error", message="timed out after 0.3s"))
    suspects = locate(t, [])
    assert [(s.span_id, s.tier, s.source) for s in suspects] == [("a", 3, "error status")]
    assert suspects[0].reason == "timed out after 0.3s" and suspects[0].span_name == "tool.a"


def test_a_check_that_names_the_run_span_does_not_outrank_the_span_that_actually_failed():
    t = traj(span("root", "agent.run", parent=None, kind="agent", status="error", message="boom"),
             span("a", "tool.a", offset=1, status="error", message="timed out"))
    suspects = locate(t, [check("task_completion", ["root"], gating=True, reason="the run failed")])
    assert [s.span_id for s in suspects] == ["a"]  # the gating signal on the root is a consequence, so it is dropped


def test_the_run_span_stays_when_a_check_names_only_it():
    t = traj(span("root", "agent.run", parent=None, kind="agent"), span("a", "tool.a", offset=1))
    assert [s.span_id for s in locate(t, [check("task_completion", ["root"], gating=True)])] == ["root"]


def test_the_run_span_is_a_suspect_only_when_nothing_beneath_it_failed():
    only_root = traj(span("root", "agent.run", parent=None, kind="agent", status="error", message="max steps exceeded"),
                     span("a", "tool.a", offset=1))
    assert [s.span_id for s in locate(only_root, [])] == ["root"]


def test_tier_order_contract_then_gating_then_reported_then_error():
    t = traj(ROOT, span("err", "tool.err", offset=1, status="error", message="x"), span("soft", "tool.soft", offset=2),
             span("hard", "tool.hard", offset=3), span("bad", "tool.bad", offset=4))
    suspects = locate(t, [check("tool_correctness", ["soft"]),
                          check("policy_compliance", ["hard"], gating=True),
                          check("tool_output_contract", ["bad"])])
    assert [(s.span_id, s.tier) for s in suspects] == [("bad", 0), ("hard", 1), ("soft", 2), ("err", 3)]


def test_earliest_span_wins_within_a_tier():
    t = traj(ROOT, span("late", "tool.late", offset=9), span("early", "tool.early", offset=1))
    suspects = locate(t, [check("policy_compliance", ["late", "early"], gating=True)])
    assert [s.span_id for s in suspects] == ["early", "late"]


def test_a_span_flagged_twice_keeps_its_strongest_signal():
    t = traj(ROOT, span("a", "tool.a", offset=1, status="error", message="e"))
    (only,) = locate(t, [check("task_completion", ["a"], gating=True, reason="gating reason")])
    assert only.tier == 1 and only.source == "task completion" and only.reason == "gating reason"


def test_passed_checks_and_unknown_span_ids_are_ignored():
    t = traj(ROOT, span("a", "tool.a", offset=1))
    assert locate(t, [check("policy_compliance", ["a"], gating=True, passed=True), check("tool_correctness", ["ghost"])]) == []


def test_it_does_not_read_stack_traces_or_exception_text_beyond_the_span_status():
    stack = [{"name": "exception", "timestamp_ns": 0, "attributes": {"exception.stacktrace": "File injector.py ... fault ..."}}]
    with_stack = traj(ROOT, span("a", "tool.a", offset=1, status="error", message="m", events=stack))
    without = traj(ROOT, span("a", "tool.a", offset=1, status="error", message="m", events=[]))
    assert locate(with_stack, []) == locate(without, [])


@pytest.mark.parametrize("tier_check", [("tool_output_contract", False, 0), ("policy_compliance", True, 1), ("step_efficiency", False, 2)])
def test_tier_assignment(tier_check):
    metric, gating, tier = tier_check
    t = traj(ROOT, span("a", "tool.a", offset=1))
    assert locate(t, [check(metric, ["a"], gating=gating)])[0].tier == tier
    assert dataclasses.is_dataclass(t)
