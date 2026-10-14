"""One plain object describing what a run did, built only from the stored (redacted) trace.

Every check reads a Trajectory, never raw spans, so span parsing lives in exactly one place.
"""
import json
from dataclasses import dataclass, field
from typing import Any

from blackbox.models import RunRecord, SpanRecord
from blackbox.telemetry import attributes as attr


@dataclass(frozen=True)
class ToolCallRecord:
    index: int  # position among tool calls, in the order they ran
    name: str
    args: dict[str, Any]
    output: Any  # parsed JSON when possible
    status: str  # "ok" | "error" | "unset"
    span_id: str
    status_message: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status != "error"


@dataclass(frozen=True)
class ModelCallRecord:
    span_id: str
    step: int | None
    requested_tools: list[dict[str, Any]]
    duration_ms: float
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True)
class Trajectory:
    run_id: str
    task: str
    run_status: str
    run_error: str | None
    final_answer: str
    root: SpanRecord | None
    tool_calls: list[ToolCallRecord]
    model_calls: list[ModelCallRecord]
    spans: list[SpanRecord] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return self.root.duration_ms if self.root else 0.0

    def calls(self, name: str) -> list[ToolCallRecord]:
        return [c for c in self.tool_calls if c.name == name]


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def as_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_trajectory(run: RunRecord, spans: list[SpanRecord]) -> Trajectory:
    ordered = sorted(spans, key=lambda s: (s.start_offset_ms, s.parent_span_id is not None))
    roots = [s for s in ordered if s.parent_span_id is None]
    root = roots[0] if roots else None

    tool_calls: list[ToolCallRecord] = []
    model_calls: list[ModelCallRecord] = []
    for s in ordered:
        if s.span_type == "tool":
            args = _json(s.attributes.get(attr.TOOL_ARGS, "{}"))
            tool_calls.append(
                ToolCallRecord(
                    index=len(tool_calls),
                    name=str(s.attributes.get(attr.GEN_AI_TOOL_NAME) or s.name.removeprefix("tool.")),
                    args=args if isinstance(args, dict) else {},
                    output=_json(s.attributes.get(attr.TOOL_OUTPUT)),
                    status=s.status,
                    span_id=s.span_id,
                    status_message=s.status_message,
                )
            )
        elif s.span_type == "llm":
            requested = _json(s.attributes.get(attr.MODEL_TOOL_CALLS, "[]"))
            model_calls.append(
                ModelCallRecord(
                    span_id=s.span_id,
                    step=as_int(s.attributes.get(attr.AGENT_STEP)),
                    requested_tools=requested if isinstance(requested, list) else [],
                    duration_ms=s.duration_ms,
                    input_tokens=as_int(s.attributes.get(attr.GEN_AI_INPUT_TOKENS)),
                    output_tokens=as_int(s.attributes.get(attr.GEN_AI_OUTPUT_TOKENS)),
                )
            )

    answer = ""
    if root is not None:
        answer = str(root.attributes.get(attr.AGENT_OUTPUT) or "")
    answer = answer or (run.final_answer or "")

    return Trajectory(
        run_id=run.run_id,
        task=run.task,
        run_status=run.status,
        run_error=run.error,
        final_answer=answer,
        root=root,
        tool_calls=tool_calls,
        model_calls=model_calls,
        spans=ordered,
    )
