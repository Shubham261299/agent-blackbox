"""Controlled failures for the failure lab, planted through two wrappers so the agent code is untouched.

  tool seam   wraps a tool function:   tool_timeout, malformed_output
  model seam  wraps a ModelClient:     wrong_tool, model_error

When a fault fires, the injector records the id of the span that is current at that moment. That is the ground
truth the lab scores trace analysis against. It is stored outside the trace, and the error messages below read
like real infrastructure errors: nothing in the trace says "injected", so the analysis cannot read the answer.
"""
import dataclasses
import functools
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from opentelemetry import trace

from blackbox.agent.errors import ModelUnavailableError, ToolTimeoutError
from blackbox.agent.tools import ToolSpec
from blackbox.llm.base import ModelClient, ModelResponse, ToolRequest

FaultKind = Literal["tool_timeout", "malformed_output", "wrong_tool", "model_error"]
HTML_ERROR_PAGE = "<html><body><h1>502 Bad Gateway</h1></body></html>"

__all__ = ["FaultInjector", "FaultSpec", "FiredFault", "HTML_ERROR_PAGE", "ModelUnavailableError", "ToolTimeoutError"]


@dataclass(frozen=True)
class FaultSpec:
    kind: FaultKind
    tool: str | None = None  # the tool, for tool faults
    occurrence: int = 1  # the n-th call of that tool, or the n-th model call (n-th tool-requesting reply for wrong_tool)
    params: Mapping[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        where = f"{self.tool} call {self.occurrence}" if self.tool else f"model call {self.occurrence}"
        return f"{self.kind} on {where}"


@dataclass
class FiredFault:
    spec: FaultSpec
    origin_span_id: str | None = None  # first span where the deviation is observable (hex, as stored)
    fired: bool = False


def _current_span_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.span_id, "016x") if ctx.is_valid else None


def _malformed(tool: str, mode: str) -> Any:
    if mode == "missing_fields":
        return {}
    if mode == "wrong_types":
        if tool == "lookup_order":
            return {"order_id": "forty-two", "status": 3, "total": "N/A", "days_since_delivery": "soon",
                    "customer_email": None, "shipping_address": 7}
        if tool == "check_refund_policy":
            return {"eligible": "yes", "reason": 7}
    return HTML_ERROR_PAGE


class FaultInjector:
    def __init__(self, specs: Sequence[FaultSpec]) -> None:
        self.faults = [FiredFault(spec) for spec in specs]
        self._calls: dict[str, int] = {}
        self._model_calls = 0
        self._tool_requesting_replies = 0
        self._pending_wrong: list[tuple[FiredFault, str, str]] = []  # (fault, tool, args as json) awaiting execution

    @property
    def fired(self) -> list[FiredFault]:
        return [f for f in self.faults if f.fired]

    # ---- tool seam ---------------------------------------------------------------
    def wrap_tools(self, registry: dict[str, ToolSpec]) -> dict[str, ToolSpec]:
        return {name: dataclasses.replace(spec, fn=self._wrap_tool(spec)) for name, spec in registry.items()}

    def _wrap_tool(self, spec: ToolSpec):
        @functools.wraps(spec.fn)  # keeps the real signature, so the agent's argument validation still works
        def wrapped(**kwargs: Any) -> Any:
            n = self._calls[spec.name] = self._calls.get(spec.name, 0) + 1
            self._mark_wrong_tool_origin(spec.name, kwargs)
            for fault in self.faults:
                s = fault.spec
                if s.tool != spec.name or s.occurrence != n or fault.fired:
                    continue
                if s.kind == "tool_timeout":
                    self._fire(fault)
                    delay = float(s.params.get("delay_s", 0.3))
                    time.sleep(delay)
                    raise ToolTimeoutError(f"{spec.name} timed out after {delay:g}s")
                if s.kind == "malformed_output":
                    self._fire(fault)
                    return _malformed(spec.name, str(s.params.get("mode", "html")))
            return spec.fn(**kwargs)

        return wrapped

    def _mark_wrong_tool_origin(self, tool: str, args: dict[str, Any]) -> None:
        key = json.dumps(args, sort_keys=True, default=str)
        for fault, want_tool, want_args in self._pending_wrong:
            if want_tool == tool and want_args == key and fault.origin_span_id is None:
                fault.origin_span_id = _current_span_id()
                fault.fired = True

    def _fire(self, fault: FiredFault) -> None:
        fault.origin_span_id = _current_span_id()
        fault.fired = True

    # ---- model seam --------------------------------------------------------------
    def wrap_model(self, model: ModelClient) -> ModelClient:
        return _FaultyModel(model, self)

    def _on_model_call(self, inner: ModelClient, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        self._model_calls += 1
        for fault in self.faults:
            if fault.spec.kind == "model_error" and fault.spec.occurrence == self._model_calls and not fault.fired:
                self._fire(fault)
                raise ModelUnavailableError(str(fault.spec.params.get("message", "model backend unavailable: connection refused")))
        response = inner.chat(messages, tools)
        if response.tool_calls:
            self._tool_requesting_replies += 1
            for fault in self.faults:
                s = fault.spec
                if s.kind == "wrong_tool" and s.occurrence == self._tool_requesting_replies and not fault.fired:
                    swap = ToolRequest(name=str(s.params["to_tool"]), arguments=dict(s.params.get("args", {})))
                    self._pending_wrong.append((fault, swap.name, json.dumps(swap.arguments, sort_keys=True, default=str)))
                    return dataclasses.replace(response, tool_calls=[swap, *response.tool_calls[1:]])
        return response


class _FaultyModel:
    """A ModelClient that behaves like the wrapped one except where a fault says otherwise."""

    def __init__(self, inner: ModelClient, injector: FaultInjector) -> None:
        self._inner = inner
        self._injector = injector
        self.provider = inner.provider
        self.name = inner.name

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        return self._injector._on_model_call(self._inner, messages, tools)
