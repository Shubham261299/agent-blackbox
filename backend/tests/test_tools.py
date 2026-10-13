import pytest

from blackbox.agent.tools import OrderDesk, ToolError


@pytest.fixture
def desk():
    return OrderDesk()


def test_registry_exposes_four_tools_with_schemas(desk):
    registry = desk.registry()
    assert set(registry) == {"lookup_order", "check_refund_policy", "issue_refund", "update_shipping_address"}
    for spec in registry.values():
        schema = spec.schema()
        assert schema["type"] == "function"
        assert schema["function"]["parameters"]["required"]


def test_lookup_order(desk):
    result = desk.lookup_order(42)
    assert result["status"] == "delivered" and result["total"] == 59.90


def test_lookup_unknown_order_raises(desk):
    with pytest.raises(ToolError, match="not found"):
        desk.lookup_order(999)


@pytest.mark.parametrize(
    "order_id, amount, eligible",
    [
        (42, 59.90, True),    # delivered 12 days ago, under the limit
        (43, 180.00, False),  # over the $100 limit
        (44, 40.00, False),   # delivered 45 days ago, outside the 30-day window
        (45, 75.00, False),   # not delivered yet
        (42, 70.00, False),   # more than the order total
    ],
)
def test_refund_policy(desk, order_id, amount, eligible):
    assert desk.check_refund_policy(order_id, amount)["eligible"] is eligible


def test_policy_accepts_numeric_strings_and_rejects_garbage(desk):
    assert desk.check_refund_policy("42", "59.90")["eligible"] is True
    with pytest.raises(ToolError, match="must be a number"):
        desk.check_refund_policy(42, "lots")
    with pytest.raises(ToolError, match="positive"):
        desk.check_refund_policy(42, -5)


def test_issue_refund_records_state_and_rejects_undelivered(desk):
    refund = desk.issue_refund(42, 59.90)
    assert refund["status"] == "issued" and desk.refunds == [refund]
    with pytest.raises(ToolError, match="status is shipped"):
        desk.issue_refund(45, 10)


def test_update_address_only_while_shipped(desk):
    assert desk.update_shipping_address(45, "1 New Road")["status"] == "updated"
    with pytest.raises(ToolError, match="delivered"):
        desk.update_shipping_address(42, "1 New Road")


def test_each_desk_has_isolated_state():
    a, b = OrderDesk(), OrderDesk()
    a.issue_refund(42, 10)
    assert b.refunds == []
