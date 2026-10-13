import inspect
import json
from dataclasses import dataclass
from typing import Any, Literal

from opentelemetry.trace import Span, Status, StatusCode, Tracer

from blackbox.agent.tools import ToolError, ToolSpec
from blackbox.llm.base import ModelClient, ModelResponse, ToolRequest
from blackbox.telemetry import attributes as attr
from blackbox.telemetry.tracing import now_ns, start_span

AGENT_NAME = "order-support-agent"
SYSTEM_PROMPT = (
    "You are an order support agent. Always look up an order before acting on it. "
    "Before issuing any refund you MUST call check_refund_policy and only refund if it says eligible. "
    "Never refund more than the policy allows. Use the tools; do not guess order details. "
    "When finished, reply with a short confirmation for the customer."
)
_MAX_MESSAGE_CHARS = 2000  # per message, so the serialized prompt stays valid JSON (redaction relies on that)


@dataclass(frozen=True)
class AgentResult:
    status: Literal["ok", "error"]
    final_answer: str | None
    error: str | None
    trace_id: str | None
    steps: int


class AgentRunner:
    def __init__(self, model: ModelClient, tools: dict[str, ToolSpec], tracer: Tracer, max_steps: int = 8) -> None:
        self._model = model
        self._tools = tools
        self._tracer = tracer
        self._max_steps = max_steps
        self._tool_schemas = [t.schema() for t in tools.values()]

    def run(self, run_id: str, task: str) -> AgentResult:
        trace_id: str | None = None
        steps = 0
        try:
            with start_span(
                self._tracer,
                "agent.run",
                {
                    attr.RUN_ID: run_id,
                    attr.SPAN_TYPE: "agent",
                    attr.GEN_AI_OPERATION: "invoke_agent",
                    attr.GEN_AI_AGENT_NAME: AGENT_NAME,
                    attr.GEN_AI_PROVIDER: self._model.provider,
                    attr.GEN_AI_REQUEST_MODEL: self._model.name,
                    attr.AGENT_INPUT: task,
                },
            ) as root:
                trace_id = format(root.get_span_context().trace_id, "032x")
                messages: list[dict[str, Any]] = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": task},
                ]
                for step in range(1, self._max_steps + 1):
                    steps = step
                    response = self._model_call(run_id, step, messages)
                    messages.append(_assistant_message(response))
                    if not response.tool_calls:
                        root.set_attribute(attr.AGENT_OUTPUT, response.content)
                        root.set_attribute(attr.AGENT_STEPS, steps)
                        return AgentResult("ok", response.content, None, trace_id, steps)
                    for call in response.tool_calls:
                        messages.append(self._tool_call(run_id, call))
                root.set_attribute(attr.AGENT_STEPS, steps)
                error = f"max steps ({self._max_steps}) exceeded without a final answer"
                root.set_status(Status(StatusCode.ERROR, error))
                return AgentResult("error", None, error, trace_id, steps)
        except Exception as exc:  # the root span has already recorded it and gone to ERROR
            return AgentResult("error", None, f"{type(exc).__name__}: {exc}", trace_id, steps)

    # ---- model call span ---------------------------------------------------------
    def _model_call(self, run_id: str, step: int, messages: list[dict[str, Any]]) -> ModelResponse:
        with start_span(
            self._tracer,
            "model.call",
            attributes={
                attr.RUN_ID: run_id,
                attr.SPAN_TYPE: "llm",
                attr.GEN_AI_OPERATION: "chat",
                attr.GEN_AI_PROVIDER: self._model.provider,
                attr.GEN_AI_REQUEST_MODEL: self._model.name,
                attr.AGENT_STEP: step,
                attr.MODEL_PROMPT: _serialize_messages(messages),
            },
        ) as span:
            response = self._model.chat(messages, self._tool_schemas)
            span.set_attribute(attr.MODEL_COMPLETION, response.content)
            if response.tool_calls:
                span.set_attribute(
                    attr.MODEL_TOOL_CALLS,
                    json.dumps([{"name": c.name, "arguments": c.arguments} for c in response.tool_calls], default=str),
                )
            if response.input_tokens is not None:
                span.set_attribute(attr.GEN_AI_INPUT_TOKENS, response.input_tokens)
            if response.output_tokens is not None:
                span.set_attribute(attr.GEN_AI_OUTPUT_TOKENS, response.output_tokens)
            span.update_name(_model_span_name(step, response))
            return response

    # ---- tool call span ----------------------------------------------------------
    def _tool_call(self, run_id: str, call: ToolRequest) -> dict[str, Any]:
        with start_span(
            self._tracer,
            f"tool.{call.name}",
            attributes={
                attr.RUN_ID: run_id,
                attr.SPAN_TYPE: "tool",
                attr.GEN_AI_OPERATION: "execute_tool",
                attr.GEN_AI_TOOL_NAME: call.name,
                attr.TOOL_ARGS: json.dumps(call.arguments, default=str),
            },
        ) as span:
            try:
                output = json.dumps(self._execute(call), default=str)
                span.set_status(Status(StatusCode.OK))
            except ToolError as exc:  # expected failure: record it, tell the model, let it recover
                _record_tool_failure(span, exc)
                output = json.dumps({"error": str(exc)})
            span.set_attribute(attr.TOOL_OUTPUT, output)
        return {"role": "tool", "tool_name": call.name, "content": output}

    def _execute(self, call: ToolRequest) -> dict[str, Any]:
        spec = self._tools.get(call.name)
        if spec is None:
            raise ToolError(f"unknown tool '{call.name}'")
        try:
            inspect.signature(spec.fn).bind(**call.arguments)
        except TypeError as exc:
            raise ToolError(f"invalid arguments for {call.name}: {exc}") from None
        return spec.fn(**call.arguments)


def _record_tool_failure(span: Span, exc: Exception) -> None:
    span.record_exception(exc, timestamp=now_ns())
    span.set_status(Status(StatusCode.ERROR, str(exc)))


def _model_span_name(step: int, response: ModelResponse) -> str:
    if not response.tool_calls:
        return "model.finalize"
    return "model.plan" if step == 1 else "model.call"


def _assistant_message(response: ModelResponse) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": response.content}
    if response.tool_calls:
        message["tool_calls"] = [{"function": {"name": c.name, "arguments": c.arguments}} for c in response.tool_calls]
    return message


def _serialize_messages(messages: list[dict[str, Any]]) -> str:
    clipped = [
        {**m, "content": m["content"][:_MAX_MESSAGE_CHARS]} if isinstance(m.get("content"), str) else m
        for m in messages
    ]
    return json.dumps(clipped, default=str)
