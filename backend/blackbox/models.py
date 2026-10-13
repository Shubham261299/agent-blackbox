from typing import Any, Literal

from pydantic import BaseModel, Field

RunStatus = Literal["running", "ok", "error"]
SpanStatus = Literal["unset", "ok", "error"]
SpanType = Literal["agent", "llm", "tool", "other"]


class RunRequest(BaseModel):
    task: str = Field(min_length=1, max_length=2000)
    model: Literal["scripted", "ollama"] = "scripted"
    # Scripted model only: which canned conversation to replay.
    scenario: str | None = None


class RunRecord(BaseModel):
    """Application-level run metadata. `status` says whether the agent run completed,
    not whether the task was done correctly -- that is the evaluation layer's job."""

    run_id: str
    task: str
    model: str
    status: RunStatus
    trace_id: str | None = None
    started_at: str
    duration_ms: float | None = None
    final_answer: str | None = None
    error: str | None = None


class SpanRecord(BaseModel):
    span_id: str
    run_id: str
    trace_id: str
    parent_span_id: str | None
    name: str
    span_type: SpanType
    start_time_ns: int
    end_time_ns: int
    duration_ms: float
    status: SpanStatus
    status_message: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
