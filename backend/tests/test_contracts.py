import pytest

from blackbox.agent.contracts import contract_problems
from blackbox.agent.tools import OrderDesk
from blackbox.evals.checks import check_tool_output_contract
from blackbox.evals.trajectory import ToolCallRecord, Trajectory

REDACTED_ORDER = {"order_id": 42, "status": "delivered", "total": 59.9, "days_since_delivery": 12,
                  "customer_email": "[REDACTED]", "shipping_address": "[REDACTED]"}


def test_every_real_tool_output_honours_its_contract():
    desk = OrderDesk()
    assert contract_problems("lookup_order", desk.lookup_order(42)) == []
    assert contract_problems("lookup_order", desk.lookup_order(45)) == []  # shipped: days_since_delivery is None
    assert contract_problems("check_refund_policy", desk.check_refund_policy(42, 10)) == []
    assert contract_problems("check_refund_policy", desk.check_refund_policy(43, 180)) == []
    assert contract_problems("issue_refund", desk.issue_refund(42, 10)) == []
    assert contract_problems("update_shipping_address", desk.update_shipping_address(45, "1 Road")) == []


def test_redacted_values_are_still_valid_strings():
    assert contract_problems("lookup_order", REDACTED_ORDER) == []  # stored traces hold [REDACTED] markers


@pytest.mark.parametrize("output, fragment", [
    ("<html><body>502</body></html>", "expected an object, got str"),
    (None, "expected an object, got NoneType"),
    ([], "expected an object, got list"),
    ({}, "missing field 'order_id'"),
    ({**REDACTED_ORDER, "status": "lost"}, "field 'status' has an invalid value 'lost'"),
    ({**REDACTED_ORDER, "total": "N/A"}, "field 'total'"),
    ({**REDACTED_ORDER, "total": True}, "field 'total'"),          # a bool is not a number
    ({**REDACTED_ORDER, "order_id": "forty-two"}, "field 'order_id'"),
    ({**REDACTED_ORDER, "days_since_delivery": "soon"}, "field 'days_since_delivery'"),
    ({**REDACTED_ORDER, "customer_email": None}, "field 'customer_email'"),
])
def test_lookup_order_violations(output, fragment):
    problems = contract_problems("lookup_order", output)
    assert any(fragment in p for p in problems), problems


def test_other_tools_violations():
    assert contract_problems("check_refund_policy", {"eligible": "yes", "reason": 7})
    assert contract_problems("check_refund_policy", {"reason": "x"}) == ["missing field 'eligible'"]
    assert any("should be 'issued'" in p for p in contract_problems("issue_refund", {"refund_id": "R1", "order_id": 1, "amount": 2, "status": "pending"}))
    assert contract_problems("issue_refund", {"refund_id": "R1", "order_id": 1, "amount": 2.5, "status": "issued"}) == []
    assert any("should be 'updated'" in p for p in contract_problems("update_shipping_address", {"order_id": 1, "shipping_address": "x", "status": "no"}))


def test_a_tool_without_a_contract_is_not_flagged():
    assert contract_problems("refund_customer", {"anything": 1}) == []


# ---------------------------------------------------------------- the check
def traj(*calls):
    records = [ToolCallRecord(index=i, name=n, args={}, output=o, status=s, span_id=f"s{i}") for i, (n, o, s) in enumerate(calls)]
    return Trajectory(run_id="r", task="t", run_status="ok", run_error=None, final_answer="x", root=None,
                      tool_calls=records, model_calls=[], spans=[])


def test_contract_check_passes_for_good_output_and_ignores_failed_calls():
    good = traj(("lookup_order", REDACTED_ORDER, "ok"), ("lookup_order", {"error": "order 999 not found"}, "error"))
    result = check_tool_output_contract(good)
    assert result.passed and not result.gating  # an error message from a failed call is not the tool's result


def test_contract_check_flags_the_span_that_returned_garbage():
    bad = traj(("lookup_order", "<html>502</html>", "ok"), ("check_refund_policy", {"eligible": True, "reason": "ok"}, "ok"))
    result = check_tool_output_contract(bad)
    assert not result.passed and result.span_ids == ["s0"]
    assert "lookup_order returned data that breaks its contract" in result.reason
