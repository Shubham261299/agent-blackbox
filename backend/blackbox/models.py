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
    variant: str = "baseline"  # agent configuration preset (blackbox.agent.config.PRESETS)


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


EvalKind = Literal["benchmark", "reference", "validation", "faultlab"]


class EvalRunSummary(BaseModel):
    eval_id: str
    kind: EvalKind
    model: str
    dataset_version: str
    dataset_hash: str
    seed: int | None = None
    variant: str = "baseline"  # which agent configuration produced the runs
    rescored_from: str | None = None  # set when this evaluation re-judged another one's stored runs (no model was run)
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


class Suspect(BaseModel):
    """A span trace analysis points at, ranked. Computed from the trace and the checks, never from the injected fault."""

    span_id: str
    span_name: str
    tier: int  # 0 contract violation, 1 failed gating check, 2 failed reported check, 3 error status
    source: str
    reason: str


class RunFault(BaseModel):
    """Ground truth for a lab run: what was planted and where. Stored outside the trace on purpose."""

    kind: str
    tool: str | None = None
    occurrence: int = 1
    description: str
    origin_span_id: str | None = None
    fired: bool = False


class RunEvaluation(BaseModel):
    """Checks for one run. `case_id`/`eval_id` are set when the run belonged to a stored evaluation;
    otherwise only the checks that need no expectations are computed on the fly."""

    run_id: str
    eval_id: str | None = None
    case_id: str | None = None
    stored: bool
    checks: list[CheckResult]
    suspects: list[Suspect] = Field(default_factory=list)


class StartEvalRequest(BaseModel):
    mode: Literal["reference", "faults", "faultlab"] = "reference"
    variant: str = "baseline"


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
    variant: str = "baseline"


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


# ---- before/after comparison of two stored evaluations ------------------------------------------------------
CaseChangeKind = Literal["fixed", "broken", "still_passing", "still_failing", "only_baseline", "only_candidate"]


class CaseChange(BaseModel):
    """One case (or, for a failure-lab comparison, one planted fault) on both sides. `passed` means the gating
    checks passed; for a lab it means the fault had no effect on the run."""

    case_id: str
    category: str
    task: str
    change: CaseChangeKind
    baseline_passed: bool | None = None
    candidate_passed: bool | None = None
    baseline_run_id: str | None = None
    candidate_run_id: str | None = None
    baseline_failed_checks: list[str] = Field(default_factory=list)
    candidate_failed_checks: list[str] = Field(default_factory=list)
    baseline_effect: str | None = None  # failure lab only: run_failed / gating_failed / silent / no_effect
    candidate_effect: str | None = None
    baseline_duration_ms: float | None = None
    candidate_duration_ms: float | None = None
    baseline_tool_calls: int | None = None
    candidate_tool_calls: int | None = None
    baseline_retries: int | None = None
    candidate_retries: int | None = None


class MetricChange(BaseModel):
    metric: str
    gating: bool
    baseline_passed: int
    baseline_total: int
    candidate_passed: int
    candidate_total: int


class CategoryChange(BaseModel):
    category: str
    total: int
    baseline_passed: int
    candidate_passed: int


class CostTotals(BaseModel):
    """What it took, over the cases both sides ran. Tokens are None when any run did not measure them."""

    cases: int
    tool_calls: int
    model_calls: int
    retries: int
    total_duration_ms: float
    median_duration_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class Comparison(BaseModel):
    kind: EvalKind
    baseline: EvalRunSummary
    candidate: EvalRunSummary
    matched: int  # cases present on both sides; the counts below only use these
    fixed: int
    broken: int
    still_passing: int
    still_failing: int
    cases: list[CaseChange]
    metrics: list[MetricChange]
    categories: list[CategoryChange]
    baseline_cost: CostTotals
    candidate_cost: CostTotals
