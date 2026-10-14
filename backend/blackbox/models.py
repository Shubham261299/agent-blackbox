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


class CheckResult(BaseModel):
    metric: str
    # None means "informational, not a pass/fail question" (latency).
    passed: bool | None
    score: float | None = None
    reason: str
    span_ids: list[str] = Field(default_factory=list)  # spans the finding is about
    details: dict[str, Any] = Field(default_factory=dict)
    gating: bool = False  # a run passes when every gating check passes


class EvalCaseResult(BaseModel):
    case_id: str
    category: str
    task: str
    run_id: str
    run_status: RunStatus
    passed: bool
    duration_ms: float | None = None
    note: dict[str, Any] | None = None  # validation batches: which fault, which checks were expected to fail
    checks: list[CheckResult] = Field(default_factory=list)


EvalKind = Literal["benchmark", "reference", "validation"]


class EvalRunSummary(BaseModel):
    eval_id: str
    kind: EvalKind
    model: str
    dataset_version: str
    dataset_hash: str
    seed: int | None = None
    started_at: str
    finished_at: str | None = None
    status: Literal["running", "done", "error"]
    n_cases: int = 0
    n_passed: int = 0


class MetricSummary(BaseModel):
    metric: str
    gating: bool
    passed: int
    total: int
    mean_score: float | None = None


class CategorySummary(BaseModel):
    category: str
    passed: int
    total: int


class EvalReport(EvalRunSummary):
    cases: list[EvalCaseResult] = Field(default_factory=list)
    metrics: list[MetricSummary] = Field(default_factory=list)
    categories: list[CategorySummary] = Field(default_factory=list)


class RunEvaluation(BaseModel):
    """Checks for one run. `case_id`/`eval_id` are set when the run belonged to a stored evaluation;
    otherwise only the checks that need no expectations are computed on the fly."""

    run_id: str
    eval_id: str | None = None
    case_id: str | None = None
    stored: bool
    checks: list[CheckResult]


class StartEvalRequest(BaseModel):
    mode: Literal["reference", "faults"] = "reference"


class ScenarioInfo(BaseModel):
    name: str
    description: str
    example_task: str


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
    # Offset from the earliest span of the run, computed with exact integer math server-side:
    # epoch nanoseconds (~1.8e18) exceed JavaScript's exact-integer range (~9e15).
    start_offset_ms: float = 0.0
    duration_ms: float
    status: SpanStatus
    status_message: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
