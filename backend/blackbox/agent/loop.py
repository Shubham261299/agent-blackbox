import inspect
import json
import time
from dataclasses import dataclass
from typing import Any, Literal

from opentelemetry.trace import Span, Status, StatusCode, Tracer

from blackbox.agent.config import AgentConfig
from blackbox.agent.contracts import contract_problems
from blackbox.agent.guidance import system_prompt, with_descriptions
from blackbox.agent.errors import TRANSIENT_MODEL_ERRORS, ToolContractViolation, ToolTimeoutError
from blackbox.agent.tools import ToolError, ToolSpec
from blackbox.llm.base import ModelClient, ModelResponse, ToolRequest
from blackbox.telemetry import attributes as attr
from blackbox.telemetry.tracing import now_ns, start_span

AGENT_NAME = "order-support-agent"
SYSTEM_PROMPT = system_prompt("v1")  # the baseline prompt; the agent uses config.prompt_version
_MAX_MESSAGE_CHARS = 2000  # per message, so the serialized prompt stays valid JSON (redaction relies on that)


@dataclass(frozen=True)
class AgentResult:
    status: Literal["ok", "error"]
    final_answer: str | None
    error: str | None
    trace_id: str | None
    steps: int


class AgentRunner:
    def __init__(self, model: ModelClient, tools: dict[str, ToolSpec], tracer: Tracer, max_steps: int = 8,
                 config: AgentConfig | None = None) -> None:
        self._config = config or AgentConfig()
        self._model = model
        self._tools = with_descriptions(tools, self._config.tool_descriptions)
        self._system_prompt = system_prompt(self._config.prompt_version)
        self._tracer = tracer
        self._max_steps = max_steps
        self._tool_schemas = [t.schema() for t in self._tools.values()]

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
                    # Only a non-baseline agent says so: a baseline trace is exactly what it was before variants existed.
                    **({attr.AGENT_VARIANT: self._config.name} if self._config.name != "baseline" else {}),
                },
            ) as root:
                trace_id = format(root.get_span_context().trace_id, "032x")
                messages: list[dict[str, Any]] = [
                    {"role": "system", "content": self._system_prompt},
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
            response = self._chat_with_retries(span, messages)
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
                output = json.dumps(self._execute_with_retries(span, call), default=str)
                span.set_status(Status(StatusCode.OK))
            except (ToolError, ToolContractViolation) as exc:  # expected failure: record it, tell the model, let it recover
                _record_tool_failure(span, exc)
                output = json.dumps({"error": str(exc)})
            except ToolTimeoutError as exc:
                if not self._config.retries:
                    raise  # the baseline agent has no handling for infrastructure failures: the run ends
                _record_tool_failure(span, exc)  # retries are spent: tell the model instead of killing the run
                output = json.dumps({"error": str(exc)})
            span.set_attribute(attr.TOOL_OUTPUT, output)
        return {"role": "tool", "tool_name": call.name, "content": output}

    def _execute_with_retries(self, span: Span, call: ToolRequest) -> dict[str, Any]:
        """Retries only what a second try can fix: a timeout, or output that broke its contract. A ToolError is an
        answer ("order not found"), so asking again would get the same one; the model decides what to do with it.
        Every attempt happens inside the one tool span, so the trace still has one span per call the model made."""
        retried = 0
        while True:
            try:
                result = self._execute(call)
                if self._config.enforce_contracts:
                    problems = contract_problems(call.name, result)
                    if problems:
                        raise ToolContractViolation(f"{call.name} returned invalid output: {'; '.join(problems)}")
                return result
            except (ToolTimeoutError, ToolContractViolation) as exc:
                if retried >= self._config.retries:
                    raise
                retried += 1
                self._note_retry(span, retried, exc)

    def _chat_with_retries(self, span: Span, messages: list[dict[str, Any]]) -> ModelResponse:
        retried = 0
        while True:
            try:
                return self._model.chat(messages, self._tool_schemas)
            except TRANSIENT_MODEL_ERRORS as exc:
                if retried >= self._config.retries:
                    raise
                retried += 1
                self._note_retry(span, retried, exc)

    def _note_retry(self, span: Span, retried: int, exc: Exception) -> None:
        span.add_event(
            "retry",
            {"retry.attempt": retried, "exception.type": f"{type(exc).__module__}.{type(exc).__qualname__}",
             "exception.message": str(exc)},
            timestamp=now_ns(),
        )
        span.set_attribute(attr.RETRY_COUNT, retried)
        if self._config.backoff_s:
            time.sleep(self._config.backoff_s * retried)

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
    # An expected domain failure: type and message are the useful part. Skipping the stack trace keeps this
    # cheap -- formatting one inside the span made a failing tool look ~100x slower than it was.
    span.add_event(
        "exception",
        {"exception.type": f"{type(exc).__module__}.{type(exc).__qualname__}", "exception.message": str(exc)},
        timestamp=now_ns(),
    )
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
