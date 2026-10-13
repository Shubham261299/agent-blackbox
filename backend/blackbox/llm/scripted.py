"""Deterministic model: replays a fixed sequence of responses. It ignores the prompt on purpose --
it exists so traces, tests and bulk eval runs are repeatable and cost nothing."""
from collections.abc import Callable
from typing import Any

from blackbox.llm.base import ModelResponse, ToolRequest


class ScriptExhausted(RuntimeError):
    pass


class ScriptedModel:
    provider = "scripted"

    def __init__(self, responses: list[ModelResponse], name: str = "scripted-v1") -> None:
        self.name = name
        self._responses = list(responses)
        self._next = 0

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        if self._next >= len(self._responses):
            raise ScriptExhausted(f"script has {len(self._responses)} responses; call {self._next + 1} requested")
        response = self._responses[self._next]
        self._next += 1
        return response


def _call(name: str, **arguments: Any) -> ModelResponse:
    return ModelResponse(tool_calls=[ToolRequest(name=name, arguments=arguments)])


def _say(text: str) -> ModelResponse:
    return ModelResponse(content=text)


SCENARIOS: dict[str, Callable[[], list[ModelResponse]]] = {
    "refund_happy_path": lambda: [
        _call("lookup_order", order_id=42),
        _call("check_refund_policy", order_id=42, amount=59.90),
        _call("issue_refund", order_id=42, amount=59.90),
        _say("I issued a refund of $59.90 for order 42 (delivered 12 days ago, within the 30-day policy)."),
    ],
    "refund_denied_over_limit": lambda: [
        _call("lookup_order", order_id=43),
        _call("check_refund_policy", order_id=43, amount=180.00),
        _say("I can't refund order 43: the $180.00 amount exceeds the $100 refund limit."),
    ],
    "unknown_order": lambda: [
        _call("lookup_order", order_id=999),
        _say("I couldn't find order 999, so I haven't changed anything. Could you double-check the order number?"),
    ],
}
DEFAULT_SCENARIO = "refund_happy_path"


def scripted_model(scenario: str | None) -> ScriptedModel:
    key = scenario or DEFAULT_SCENARIO
    if key not in SCENARIOS:
        raise KeyError(key)
    return ScriptedModel(SCENARIOS[key](), name=key)
