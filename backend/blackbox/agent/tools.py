"""Mock order-support tools. All data is fictional; some fields are PII on purpose so redaction is observable."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

REFUND_WINDOW_DAYS = 30
REFUND_MAX_AMOUNT = 100.0


class ToolError(Exception):
    """A domain-level tool failure (unknown order, rule violation). The agent sees the message and may recover."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., dict[str, Any]]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


def _amount(value: Any) -> float:
    """Models sometimes send numbers as strings; accept those, reject anything else with a clear error."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ToolError(f"amount must be a number, got {value!r}") from None
    if amount <= 0:
        raise ToolError("amount must be positive")
    return amount


def _seed_orders() -> dict[int, dict[str, Any]]:
    return {
        42: {"status": "delivered", "total": 59.90, "days_since_delivery": 12,
             "customer_email": "ava.martin@example.com", "shipping_address": "12 Birch Lane, Springfield"},
        43: {"status": "delivered", "total": 180.00, "days_since_delivery": 10,
             "customer_email": "noah.kim@example.com", "shipping_address": "9 Harbor Road, Riverton"},
        44: {"status": "delivered", "total": 40.00, "days_since_delivery": 45,
             "customer_email": "mia.chen@example.com", "shipping_address": "301 Pine Street, Lakeside"},
        45: {"status": "shipped", "total": 75.00, "days_since_delivery": None,
             "customer_email": "leo.silva@example.com", "shipping_address": "77 Cedar Court, Oakdale"},
    }


class OrderDesk:
    """In-memory order store plus the four tools bound to it. One instance per run."""

    def __init__(self) -> None:
        self.orders = _seed_orders()
        self.refunds: list[dict[str, Any]] = []

    # ---- tools -----------------------------------------------------------------
    def lookup_order(self, order_id: int) -> dict[str, Any]:
        return {"order_id": order_id, **self._order(order_id)}

    def check_refund_policy(self, order_id: int, amount: float) -> dict[str, Any]:
        order = self._order(order_id)
        amount = _amount(amount)
        if order["status"] != "delivered":
            return {"eligible": False, "reason": f"order is {order['status']}, not delivered"}
        if order["days_since_delivery"] > REFUND_WINDOW_DAYS:
            return {"eligible": False, "reason": f"delivered {order['days_since_delivery']} days ago, window is {REFUND_WINDOW_DAYS}"}
        if amount > REFUND_MAX_AMOUNT:
            return {"eligible": False, "reason": f"amount exceeds the ${REFUND_MAX_AMOUNT:.0f} refund limit"}
        if amount > order["total"]:
            return {"eligible": False, "reason": "amount exceeds the order total"}
        return {"eligible": True, "reason": f"within {REFUND_WINDOW_DAYS} days and under ${REFUND_MAX_AMOUNT:.0f}"}

    def issue_refund(self, order_id: int, amount: float) -> dict[str, Any]:
        order = self._order(order_id)
        amount = _amount(amount)
        if order["status"] != "delivered":
            raise ToolError(f"cannot refund order {order_id}: status is {order['status']}")
        refund = {"refund_id": f"R-{order_id}-{len(self.refunds) + 1}", "order_id": order_id,
                  "amount": amount, "status": "issued"}
        self.refunds.append(refund)
        return refund

    def update_shipping_address(self, order_id: int, new_address: str) -> dict[str, Any]:
        order = self._order(order_id)
        if order["status"] != "shipped":
            raise ToolError(f"address can only change while an order is shipped; order {order_id} is {order['status']}")
        order["shipping_address"] = new_address
        return {"order_id": order_id, "shipping_address": new_address, "status": "updated"}

    # ---- registry --------------------------------------------------------------
    def registry(self) -> dict[str, ToolSpec]:
        order_id = {"type": "integer", "description": "The numeric order id"}
        specs = [
            ToolSpec("lookup_order", "Look up an order by id: status, total, days since delivery, customer details.",
                     {"type": "object", "properties": {"order_id": order_id}, "required": ["order_id"]},
                     self.lookup_order),
            ToolSpec("check_refund_policy", "Check whether a refund amount is allowed for an order. Call before issue_refund.",
                     {"type": "object",
                      "properties": {"order_id": order_id, "amount": {"type": "number", "description": "Refund amount in dollars"}},
                      "required": ["order_id", "amount"]},
                     self.check_refund_policy),
            ToolSpec("issue_refund", "Issue a refund for a delivered order.",
                     {"type": "object",
                      "properties": {"order_id": order_id, "amount": {"type": "number", "description": "Refund amount in dollars"}},
                      "required": ["order_id", "amount"]},
                     self.issue_refund),
            ToolSpec("update_shipping_address", "Change the shipping address of an order that has not been delivered yet.",
                     {"type": "object",
                      "properties": {"order_id": order_id, "new_address": {"type": "string"}},
                      "required": ["order_id", "new_address"]},
                     self.update_shipping_address),
        ]
        return {s.name: s for s in specs}

    # ---- internals -------------------------------------------------------------
    def _order(self, order_id: int) -> dict[str, Any]:
        try:
            return self.orders[int(order_id)]
        except (KeyError, ValueError, TypeError):
            raise ToolError(f"order {order_id} not found") from None
