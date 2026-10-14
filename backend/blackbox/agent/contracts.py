"""What a *successful* tool call must return. Used by the tool_output_contract check today, and available
to enforce at runtime later. Kept to plain Python: required keys and types, no schema library."""
from collections.abc import Callable
from typing import Any


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check(output: Any, fields: dict[str, Callable[[Any], bool]], expected: dict[str, Any] | None = None) -> list[str]:
    if not isinstance(output, dict):
        kind = type(output).__name__
        preview = output[:40] + "…" if isinstance(output, str) and len(output) > 40 else output
        return [f"expected an object, got {kind}: {preview!r}"]
    problems = []
    for name, ok in fields.items():
        if name not in output:
            problems.append(f"missing field {name!r}")
        elif not ok(output[name]):
            problems.append(f"field {name!r} has an invalid value {output[name]!r}")
    for name, want in (expected or {}).items():
        if name in output and output[name] != want:
            problems.append(f"field {name!r} should be {want!r}, got {output[name]!r}")
    return problems


def _lookup_order(output: Any) -> list[str]:
    return _check(output, {
        "order_id": _is_int,
        "status": lambda v: v in ("delivered", "shipped"),
        "total": _is_number,
        "days_since_delivery": lambda v: v is None or _is_int(v),
        "customer_email": lambda v: isinstance(v, str),   # stored traces hold "[REDACTED]": still a string
        "shipping_address": lambda v: isinstance(v, str),
    })


def _check_refund_policy(output: Any) -> list[str]:
    return _check(output, {"eligible": lambda v: isinstance(v, bool), "reason": lambda v: isinstance(v, str)})


def _issue_refund(output: Any) -> list[str]:
    return _check(output, {"refund_id": lambda v: isinstance(v, str), "order_id": _is_int, "amount": _is_number},
                  {"status": "issued"})


def _update_shipping_address(output: Any) -> list[str]:
    return _check(output, {"order_id": _is_int, "shipping_address": lambda v: isinstance(v, str)}, {"status": "updated"})


CONTRACTS: dict[str, Callable[[Any], list[str]]] = {
    "lookup_order": _lookup_order,
    "check_refund_policy": _check_refund_policy,
    "issue_refund": _issue_refund,
    "update_shipping_address": _update_shipping_address,
}


def contract_problems(tool: str, output: Any) -> list[str]:
    """Problems with a successful call's output, or [] if it honours the contract (or the tool has none)."""
    validate = CONTRACTS.get(tool)
    return validate(output) if validate else []
