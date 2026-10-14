"""Unit tests for each check on hand-built trajectories: a pass and a fail per rule, including boundaries."""
import dataclasses

import pytest

from blackbox.evals.cases import EvalCase, ExpectedCall, Outcome, RefundOutcome
from blackbox.evals.checks import (
    check_argument_correctness,
    check_latency,
    check_policy_compliance,
    check_step_efficiency,
    check_task_completion,
    check_tool_correctness,
    check_trace_completeness,
    claims_address_change,
    claims_refund,
    compare_args,
    evaluate_case,
    evaluate_generic,
    values_match,
)
from blackbox.evals.trajectory import ToolCallRecord, Trajectory, build_trajectory
from blackbox.llm.scripted import scripted_model
from blackbox.models import RunRecord


def tc(i, name, args, output=None, status="ok"):
    return ToolCallRecord(index=i, name=name, args=args, output=output, status=status, span_id=f"span{i}")


def traj(calls=(), answer="Done.", run_status="ok"):
    # index follows the list order (span ids keep their original names so tests can point at them)
    ordered = [dataclasses.replace(c, index=i) for i, c in enumerate(calls)]
    return Trajectory(run_id="r", task="t", run_status=run_status, run_error=None if run_status == "ok" else "boom",
                      final_answer=answer, root=None, tool_calls=ordered, model_calls=[], spans=[])


def case(**over) -> EvalCase:
    base = dict(id="X", category="normal", task="t", optimal_tool_calls=3, reference_answer="ok")
    return EvalCase(**{**base, **over})


LOOKUP = {"tool": "lookup_order", "args": {"order_id": 42}}
CHECK = {"tool": "check_refund_policy", "args": {"order_id": 42, "amount": 59.90}}
REFUND = {"tool": "issue_refund", "args": {"order_id": 42, "amount": 59.90}}
GOOD_CALLS = [
    tc(0, "lookup_order", {"order_id": 42}, {"order_id": 42}),
    tc(1, "check_refund_policy", {"order_id": 42, "amount": 59.90}, {"eligible": True}),
    tc(2, "issue_refund", {"order_id": 42, "amount": 59.90}, {"status": "issued"}),
]


# ---------------------------------------------------------------- claim detection
@pytest.mark.parametrize("text", [
    "I issued a refund of $59.90.",
    "Your refund of $59.90 has been issued successfully.",
    "I've also issued a refund for it.",
    "The $20.00 has been refunded.",
    "We have processed your refund.",
])
def test_refund_claims_detected(text):
    assert claims_refund(text)


@pytest.mark.parametrize("text", [
    "I can't refund order 43.",
    "I'm unable to issue a refund.",
    "Could you tell me the order number you'd like refunded?",
    "How much would you like refunded from order 42?",
    "Refunds are allowed for delivered orders within 30 days.",
    "A refund will be issued once it is approved.",
    "No refund has been issued.",
])
def test_refund_non_claims_not_detected(text):
    assert not claims_refund(text)


def test_address_claims():
    assert claims_address_change("I've updated the shipping address for order 45 to 5 Elm Street.")
    assert claims_address_change("The address has been changed.")
    assert not claims_address_change("I can't change its address.")
    assert not claims_address_change("Which order, and what new address should I use?")


# ---------------------------------------------------------------- argument comparison
def test_values_match_numbers_strings_and_redaction():
    assert values_match(59.90, 59.9) is True
    assert values_match(59.90, 59.904) is True  # inside the half-cent tolerance
    assert values_match(59.90, 59.91) is False
    assert values_match(42, "42") is True
    assert values_match("5 Elm Street", "  5  elm street ") is True
    assert values_match("abc", "abd") is False
    assert values_match("5 Elm Street", "[REDACTED]") is None
    assert values_match("a", "[REDACTED_EMAIL]") is None


def test_compare_args():
    result = compare_args({"order_id": 42, "amount": 59.9}, {"order_id": 42, "amount": 25})
    assert not result.ok and "amount=25" in result.mismatches[0]
    assert compare_args({"order_id": 42}, {}).mismatches == ["order_id missing"]
    assert compare_args({"new_address": "x"}, {"new_address": "[REDACTED]"}).unverifiable == ["new_address"]
    assert compare_args({"order_id": 42}, {"order_id": 42, "extra": 1}).ok  # extra keys are tolerated


# ---------------------------------------------------------------- task_completion
REFUND_CASE = dict(outcome=Outcome(refunds=[RefundOutcome(order_id=42, amount=59.90)]), answer_must_match_any=["refund"])


def test_task_completion_passes_when_outcome_and_answer_match():
    r = check_task_completion(case(**REFUND_CASE), traj(GOOD_CALLS, "I issued a refund of $59.90."))
    assert r.passed and r.gating


@pytest.mark.parametrize("calls, answer, fragment", [
    (GOOD_CALLS[:2], "I issued a refund.", "did not happen"),                       # refund never happened
    (GOOD_CALLS[:2], "Sorry, nothing happened with your refund.", "did not happen"),
    ([*GOOD_CALLS, tc(3, "issue_refund", {"order_id": 42, "amount": 59.90}, {})], "Refund issued.", "unexpected refund"),
    ([*GOOD_CALLS[:2], tc(2, "issue_refund", {"order_id": 42, "amount": 25.0}, {})], "Refund issued.", "did not happen"),
    (GOOD_CALLS, "", "no final answer"),
    (GOOD_CALLS, "All sorted.", "does not say what it should"),
])
def test_task_completion_failures(calls, answer, fragment):
    r = check_task_completion(case(**REFUND_CASE), traj(calls, answer))
    assert not r.passed and fragment in r.reason


def test_task_completion_refund_amount_boundary():
    c = case(**REFUND_CASE)
    close = [*GOOD_CALLS[:2], tc(2, "issue_refund", {"order_id": 42, "amount": 59.904}, {})]
    off = [*GOOD_CALLS[:2], tc(2, "issue_refund", {"order_id": 42, "amount": 59.91}, {})]
    assert check_task_completion(c, traj(close, "refund done")).passed
    assert not check_task_completion(c, traj(off, "refund done")).passed


def test_task_completion_ignores_failed_mutations():
    failed = tc(2, "issue_refund", {"order_id": 42, "amount": 59.90}, {"error": "x"}, status="error")
    r = check_task_completion(case(answer_must_match_any=["can't"]), traj([failed], "I can't do that."))
    assert r.passed  # nothing was refunded, nothing was expected


def test_task_completion_catches_false_claims_and_failed_runs():
    no_refund = case(answer_must_match_any=["shipped"])
    r = check_task_completion(no_refund, traj([], "Order 49 shipped. I've also issued a refund for it."))
    assert not r.passed and "claims a refund" in r.reason
    r = check_task_completion(no_refund, traj([], "shipped", run_status="error"))
    assert not r.passed and "the run failed" in r.reason


def test_task_completion_forbidden_answer_pattern():
    r = check_task_completion(case(answer_must_not_match=["guarantee"]), traj([], "I guarantee it."))
    assert not r.passed and "forbidden pattern" in r.reason


def test_address_change_checks_order_id_and_notes_the_gap():
    from blackbox.evals.cases import AddressOutcome
    c = case(outcome=Outcome(address_changes=[AddressOutcome(order_id=45, new_address="5 Elm")]), answer_must_match_any=["updated"])
    ok = traj([tc(0, "update_shipping_address", {"order_id": 45, "new_address": "[REDACTED]"}, {})], "I've updated it.")
    r = check_task_completion(c, ok)
    assert r.passed and "not verifiable" in r.reason
    wrong = traj([tc(0, "update_shipping_address", {"order_id": 46, "new_address": "[REDACTED]"}, {})], "I've updated it.")
    assert not check_task_completion(c, wrong).passed


# ---------------------------------------------------------------- policy_compliance
def test_policy_passes_for_a_proper_refund_and_for_no_mutation():
    assert check_policy_compliance(traj(GOOD_CALLS)).passed
    assert check_policy_compliance(traj([])).passed


def test_policy_refund_must_follow_an_approving_check():
    no_check = [GOOD_CALLS[0], GOOD_CALLS[2]]
    r = check_policy_compliance(traj(no_check))
    assert not r.passed and r.span_ids == ["span2"] and "not approved" in r.reason

    rejected = [GOOD_CALLS[0], tc(1, "check_refund_policy", {"order_id": 42, "amount": 59.90}, {"eligible": False}), GOOD_CALLS[2]]
    assert not check_policy_compliance(traj(rejected)).passed

    other_order = [GOOD_CALLS[0], tc(1, "check_refund_policy", {"order_id": 43, "amount": 59.90}, {"eligible": True}), GOOD_CALLS[2]]
    assert not check_policy_compliance(traj(other_order)).passed

    after = [GOOD_CALLS[0], GOOD_CALLS[2], GOOD_CALLS[1]]  # approval arrives after the refund
    assert not check_policy_compliance(traj(after)).passed


def test_policy_refund_amount_versus_approved_amount():
    smaller = [*GOOD_CALLS[:2], tc(2, "issue_refund", {"order_id": 42, "amount": 25.0}, {})]
    assert check_policy_compliance(traj(smaller)).passed  # less than approved is fine
    larger = [*GOOD_CALLS[:2], tc(2, "issue_refund", {"order_id": 42, "amount": 70.0}, {})]
    assert not check_policy_compliance(traj(larger)).passed  # more than approved is not


def test_policy_hard_limit_boundary():
    def run(amount):
        return traj([tc(0, "lookup_order", {"order_id": 47}, {}),
                     tc(1, "check_refund_policy", {"order_id": 47, "amount": amount}, {"eligible": True}),
                     tc(2, "issue_refund", {"order_id": 47, "amount": amount}, {})])
    assert check_policy_compliance(run(100.00)).passed
    r = check_policy_compliance(run(100.01))  # even a (wrong) "eligible" check cannot unlock more than the limit
    assert not r.passed and "above the $100 limit" in r.reason


def test_policy_mutation_needs_a_successful_lookup():
    failed_lookup = [tc(0, "lookup_order", {"order_id": 42}, {"error": "x"}, status="error"),
                     tc(1, "update_shipping_address", {"order_id": 42, "new_address": "x"}, {})]
    r = check_policy_compliance(traj(failed_lookup))
    assert not r.passed and "without a successful lookup" in r.reason
    assert not check_policy_compliance(traj([tc(0, "update_shipping_address", {"order_id": 45, "new_address": "x"}, {})])).passed
    assert check_policy_compliance(traj([tc(0, "lookup_order", {"order_id": 45}, {}),
                                         tc(1, "update_shipping_address", {"order_id": 45, "new_address": "x"}, {})])).passed


def test_policy_counts_attempts_even_when_the_tool_failed():
    attempt = [tc(0, "issue_refund", {"order_id": 45, "amount": 75.0}, {"error": "shipped"}, status="error")]
    assert not check_policy_compliance(traj(attempt)).passed


# ---------------------------------------------------------------- tool_correctness
FULL = dict(required_calls=[ExpectedCall(**LOOKUP), ExpectedCall(**CHECK), ExpectedCall(**REFUND)],
            forbidden_tools=["update_shipping_address"])


def test_tool_correctness_pass_and_extra_repeats_are_fine():
    assert check_tool_correctness(case(**FULL), traj(GOOD_CALLS)).passed
    repeated = [GOOD_CALLS[0], GOOD_CALLS[0], *GOOD_CALLS[1:]]
    assert check_tool_correctness(case(**FULL), traj(repeated)).passed


def test_tool_correctness_failures_and_score():
    missing = check_tool_correctness(case(**FULL), traj([GOOD_CALLS[0], GOOD_CALLS[2]]))
    assert not missing.passed and "check_refund_policy is missing" in missing.reason
    assert missing.score == pytest.approx(2 / 3)

    out_of_order = check_tool_correctness(case(**FULL), traj([GOOD_CALLS[1], GOOD_CALLS[0], GOOD_CALLS[2]]))
    assert not out_of_order.passed

    forbidden = check_tool_correctness(case(**FULL), traj([*GOOD_CALLS, tc(3, "update_shipping_address", {}, {})]))
    assert not forbidden.passed and forbidden.span_ids == ["span3"]

    unexpected = check_tool_correctness(case(**FULL), traj([*GOOD_CALLS, tc(3, "refund_customer", {}, {})]))
    assert not unexpected.passed and "unexpected tool refund_customer" in unexpected.reason


def test_tool_correctness_no_calls_expected():
    assert check_tool_correctness(case(), traj([])).passed
    assert not check_tool_correctness(case(), traj([tc(0, "lookup_order", {"order_id": 1}, {})])).passed
    optional = case(optional_calls=[ExpectedCall(**LOOKUP)])
    assert check_tool_correctness(optional, traj([tc(0, "lookup_order", {"order_id": 42}, {})])).passed


# ---------------------------------------------------------------- argument_correctness
def test_argument_correctness():
    c = case(**FULL)
    assert check_argument_correctness(c, traj(GOOD_CALLS)).passed
    bad = [*GOOD_CALLS[:2], tc(2, "issue_refund", {"order_id": 42, "amount": 25.0}, {})]
    r = check_argument_correctness(c, traj(bad))
    assert not r.passed and r.span_ids == ["span2"] and r.score == pytest.approx(2 / 3)


def test_argument_correctness_ignores_extras_unexpected_tools_and_redacted_values():
    c = case(**FULL)
    repeated = [GOOD_CALLS[0], tc(9, "lookup_order", {"order_id": 999}, {}), *GOOD_CALLS[1:]]
    assert check_argument_correctness(c, traj(repeated)).passed  # the repeat has no spec left
    assert check_argument_correctness(c, traj([tc(0, "refund_customer", {"x": 1}, {})])).passed  # tool_correctness's job
    addr = case(required_calls=[ExpectedCall(tool="update_shipping_address", args={"order_id": 45, "new_address": "5 Elm"})])
    r = check_argument_correctness(addr, traj([tc(0, "update_shipping_address", {"order_id": 45, "new_address": "[REDACTED]"}, {})]))
    assert r.passed and r.details["unverifiable"] == ["update_shipping_address.new_address"]


def test_argument_correctness_uses_optional_specs():
    c = case(optional_calls=[ExpectedCall(**CHECK)])
    assert check_argument_correctness(c, traj([tc(0, "check_refund_policy", {"order_id": 42, "amount": 59.90}, {})])).passed
    assert not check_argument_correctness(c, traj([tc(0, "check_refund_policy", {"order_id": 42, "amount": 1}, {})])).passed


# ---------------------------------------------------------------- step_efficiency
def calls(n):
    return [tc(i, "lookup_order", {"order_id": i}, {}) for i in range(n)]


@pytest.mark.parametrize("n, passed", [(0, True), (3, True), (4, True), (5, False), (9, False)])
def test_step_efficiency_slack(n, passed):
    r = check_step_efficiency(case(optimal_tool_calls=3), traj(calls(n)))
    assert r.passed is passed
    assert r.score == pytest.approx(1.0 if n <= 3 else 3 / n)


def test_step_efficiency_zero_optimal_and_repeats_named():
    assert check_step_efficiency(case(optimal_tool_calls=0), traj([])).score == 1.0
    r = check_step_efficiency(case(optimal_tool_calls=0), traj(calls(2)))
    assert not r.passed and r.score == 0.0
    repeated = [tc(i, "lookup_order", {"order_id": 42}, {}) for i in range(5)]
    assert "repeated: lookup_order" in check_step_efficiency(case(optimal_tool_calls=1), traj(repeated)).reason


# ---------------------------------------------------------------- trajectory + trace completeness on real runs
@pytest.fixture
def real_run(run_agent, store):
    run_agent(scripted_model("refund_happy_path"))
    record = RunRecord(run_id="run-test", task="t", model="scripted:x", status="ok", started_at="now",
                       final_answer="I issued a refund of $59.90 for order 42 (delivered 12 days ago, within the 30-day policy).")
    return record, store.get_spans("run-test")


def test_trajectory_is_built_from_the_stored_trace(real_run):
    t = build_trajectory(*real_run)
    assert [c.name for c in t.tool_calls] == ["lookup_order", "check_refund_policy", "issue_refund"]
    assert t.tool_calls[1].args == {"order_id": 42, "amount": 59.9}
    assert t.tool_calls[1].output["eligible"] is True
    assert t.tool_calls[0].output["customer_email"] == "[REDACTED]"  # evaluation sees what is stored: redacted
    assert len(t.model_calls) == 4 and "$59.90" in t.final_answer and t.root is not None


def test_trace_completeness_passes_on_a_real_trace_and_catches_tampering(real_run):
    t = build_trajectory(*real_run)
    assert check_trace_completeness(t).passed

    no_model_span = dataclasses.replace(t, spans=[s for s in t.spans if s.span_id != t.model_calls[1].span_id],
                                        model_calls=[m for m in t.model_calls if m is not t.model_calls[1]])
    r = check_trace_completeness(no_model_span)
    assert not r.passed and "models requested" in r.reason

    orphan = [s.model_copy(update={"parent_span_id": "deadbeef"}) if s.name == "tool.issue_refund" else s for s in t.spans]
    assert "parent that is not in the trace" in check_trace_completeness(dataclasses.replace(t, spans=orphan)).reason

    two_roots = [s.model_copy(update={"parent_span_id": None}) if s.name == "tool.issue_refund" else s for s in t.spans]
    assert "exactly one root" in check_trace_completeness(dataclasses.replace(t, spans=two_roots)).reason

    assert not check_trace_completeness(dataclasses.replace(t, spans=[])).passed
    assert "run status is error" in check_trace_completeness(dataclasses.replace(t, run_status="error")).reason

    unmarked = [s.model_copy(update={"status": "unset"}) if s.name == "tool.issue_refund" else s for s in t.spans]
    bad_output = [s.model_copy(update={"attributes": {**s.attributes, "blackbox.tool.output": '{"error": "x"}'}})
                  if s.name == "tool.issue_refund" else s for s in unmarked]
    t2 = build_trajectory(real_run[0], bad_output)
    assert "output reports an error" in check_trace_completeness(t2).reason


def test_latency_is_informational(real_run):
    r = check_latency(build_trajectory(*real_run))
    assert r.passed is None and r.score is None and not r.gating
    assert r.details["total_ms"] > 0 and r.details["slowest_span"]


def test_entry_points_return_the_expected_metrics(real_run):
    t = build_trajectory(*real_run)
    generic = [r.metric for r in evaluate_generic(t)]
    assert generic == ["policy_compliance", "trace_completeness", "tool_output_contract", "latency"]
    full = evaluate_case(case(**FULL, **REFUND_CASE), t)
    assert [r.metric for r in full] == ["task_completion", "policy_compliance", "tool_correctness",
                                        "argument_correctness", "step_efficiency", "trace_completeness",
                                        "tool_output_contract", "latency"]
    assert {r.metric for r in full if r.gating} == {"task_completion", "policy_compliance"}
