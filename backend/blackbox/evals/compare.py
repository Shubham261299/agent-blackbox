"""Before/after comparison of two stored evaluations.

The numbers that matter are not the two pass rates but what changed underneath them: cases that were failing and
now pass (fixed), cases that were passing and now fail (broken, the regression), and what the change cost. Only
cases both sides ran are counted, and two evaluations are only comparable when they ran the same dataset content
on the same model, so a difference cannot come from a different test or a different model.

For a failure-lab comparison the unit is a planted fault and "passed" means the fault had no effect on the run
(not whether trace analysis located it): the question is whether the agent now survives the fault.
"""
import statistics
from collections.abc import Iterable
from typing import NamedTuple

from blackbox.models import (
    CaseChange,
    CategoryChange,
    Comparison,
    CostTotals,
    EvalCaseResult,
    EvalReport,
    EvalRunSummary,
    MetricChange,
)
from blackbox.store.db import Store
from blackbox.telemetry import attributes as attr

COMPARABLE_KINDS = ("benchmark", "reference", "faultlab")


class ComparisonError(ValueError):
    """The two evaluations cannot be fairly compared. The message says why, in plain words."""


class RunCost(NamedTuple):
    tool_calls: int
    model_calls: int
    retries: int
    input_tokens: int | None  # None when any model call of the run did not report tokens
    output_tokens: int | None


def _check_comparable(baseline: EvalReport, candidate: EvalReport) -> None:
    if baseline.eval_id == candidate.eval_id:
        raise ComparisonError("An evaluation cannot be compared with itself.")
    for report in (baseline, candidate):
        if report.kind not in COMPARABLE_KINDS:
            raise ComparisonError(f"{report.eval_id} is a {report.kind} evaluation: it checks the checks, not an agent, "
                                  "so there is nothing to compare.")
    if baseline.kind != candidate.kind:
        raise ComparisonError(f"These are different kinds of evaluation ({baseline.kind} and {candidate.kind}).")
    unfinished = [r.eval_id for r in (baseline, candidate) if r.status != "done"]
    if unfinished:
        raise ComparisonError(f"{', '.join(unfinished)} has not finished.")
    if baseline.dataset_hash != candidate.dataset_hash:
        raise ComparisonError(
            f"They ran different cases ({baseline.dataset_version} {baseline.dataset_hash} against "
            f"{candidate.dataset_version} {candidate.dataset_hash}), so the difference could come from the test.")
    if baseline.model != candidate.model:
        raise ComparisonError(f"They used different models ({baseline.model} and {candidate.model}).")
    if baseline.seed != candidate.seed:
        raise ComparisonError(f"They used different seeds ({baseline.seed} and {candidate.seed}).")


def _failed(case: EvalCaseResult) -> list[str]:
    return [c.metric for c in case.checks if c.passed is False]


def _good(case: EvalCaseResult, lab: bool) -> bool:
    return (case.note or {}).get("effect") == "no_effect" if lab else case.passed


def _run_cost(store: Store, run_id: str) -> RunCost:
    spans = store.get_spans(run_id)
    models = [s for s in spans if s.span_type == "llm"]
    tokens_in = [s.attributes.get(attr.GEN_AI_INPUT_TOKENS) for s in models]
    tokens_out = [s.attributes.get(attr.GEN_AI_OUTPUT_TOKENS) for s in models]
    measured = bool(models) and all(t is not None for t in tokens_in + tokens_out)
    return RunCost(
        tool_calls=sum(1 for s in spans if s.span_type == "tool"), model_calls=len(models),
        retries=sum(int(s.attributes.get(attr.RETRY_COUNT, 0)) for s in spans),
        input_tokens=sum(tokens_in) if measured else None, output_tokens=sum(tokens_out) if measured else None,
    )


def _totals(costs: list[RunCost], durations: list[float | None]) -> CostTotals:
    known = [d for d in durations if d is not None]
    measured = bool(costs) and all(c.input_tokens is not None and c.output_tokens is not None for c in costs)
    return CostTotals(
        cases=len(costs), tool_calls=sum(c.tool_calls for c in costs), model_calls=sum(c.model_calls for c in costs),
        retries=sum(c.retries for c in costs), total_duration_ms=sum(known),
        median_duration_ms=statistics.median(known) if known else None,
        input_tokens=sum(c.input_tokens or 0 for c in costs) if measured else None,
        output_tokens=sum(c.output_tokens or 0 for c in costs) if measured else None,
    )


def _change(before: EvalCaseResult | None, after: EvalCaseResult | None, lab: bool) -> str:
    if before is None:
        return "only_candidate"
    if after is None:
        return "only_baseline"
    was, now = _good(before, lab), _good(after, lab)
    if not was and now:
        return "fixed"
    if was and not now:
        return "broken"
    return "still_passing" if now else "still_failing"


def _metric_changes(baseline: Iterable[EvalCaseResult], candidate: Iterable[EvalCaseResult]) -> list[MetricChange]:
    def tally(cases: Iterable[EvalCaseResult]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for case in cases:
            for c in case.checks:
                if c.passed is None:  # informational (latency): not a pass/fail question
                    continue
                row = out.setdefault(c.metric, {"gating": c.gating, "passed": 0, "total": 0})
                row["passed"] += 1 if c.passed else 0
                row["total"] += 1
        return out

    a, b = tally(baseline), tally(candidate)
    empty = {"gating": False, "passed": 0, "total": 0}
    metrics = sorted(set(a) | set(b), key=lambda m: (not (a.get(m) or b[m])["gating"], m))  # gating checks first
    return [
        MetricChange(metric=m, gating=(a.get(m) or b[m])["gating"],
                     baseline_passed=a.get(m, empty)["passed"], baseline_total=a.get(m, empty)["total"],
                     candidate_passed=b.get(m, empty)["passed"], candidate_total=b.get(m, empty)["total"])
        for m in metrics
    ]


def _summary(report: EvalReport) -> EvalRunSummary:
    return EvalRunSummary(**{name: getattr(report, name) for name in EvalRunSummary.model_fields})


def compare(store: Store, baseline: EvalReport, candidate: EvalReport) -> Comparison:
    _check_comparable(baseline, candidate)
    lab = baseline.kind == "faultlab"
    before = {c.case_id: c for c in baseline.cases}
    after = {c.case_id: c for c in candidate.cases}
    ordered = [c.case_id for c in baseline.cases] + [c.case_id for c in candidate.cases if c.case_id not in before]

    changes: list[CaseChange] = []
    base_costs: list[RunCost] = []
    cand_costs: list[RunCost] = []
    base_durations: list[float | None] = []
    cand_durations: list[float | None] = []
    for case_id in ordered:
        b, c = before.get(case_id), after.get(case_id)
        ref = b or c
        assert ref is not None
        bc = _run_cost(store, b.run_id) if b else None
        cc = _run_cost(store, c.run_id) if c else None
        if b and c and bc and cc:  # cost only counts cases both sides ran
            base_costs.append(bc)
            cand_costs.append(cc)
            base_durations.append(b.duration_ms)
            cand_durations.append(c.duration_ms)
        changes.append(CaseChange(
            case_id=case_id, category=ref.category, task=ref.task, change=_change(b, c, lab),
            baseline_passed=_good(b, lab) if b else None, candidate_passed=_good(c, lab) if c else None,
            baseline_run_id=b.run_id if b else None, candidate_run_id=c.run_id if c else None,
            baseline_failed_checks=_failed(b) if b else [], candidate_failed_checks=_failed(c) if c else [],
            baseline_effect=(b.note or {}).get("effect") if b and lab else None,
            candidate_effect=(c.note or {}).get("effect") if c and lab else None,
            baseline_duration_ms=b.duration_ms if b else None, candidate_duration_ms=c.duration_ms if c else None,
            baseline_tool_calls=bc.tool_calls if bc else None, candidate_tool_calls=cc.tool_calls if cc else None,
            baseline_retries=bc.retries if bc else None, candidate_retries=cc.retries if cc else None,
        ))

    shared = [x.case_id for x in changes if x.change not in ("only_baseline", "only_candidate")]
    categories: dict[str, list[int]] = {}  # category -> [total, baseline passed, candidate passed]
    for case_id in shared:
        row = categories.setdefault(before[case_id].category, [0, 0, 0])
        row[0] += 1
        row[1] += _good(before[case_id], lab)
        row[2] += _good(after[case_id], lab)
    count = lambda kind: sum(1 for x in changes if x.change == kind)  # noqa: E731
    return Comparison(
        kind=baseline.kind, baseline=_summary(baseline), candidate=_summary(candidate), matched=len(shared),
        fixed=count("fixed"), broken=count("broken"), still_passing=count("still_passing"),
        still_failing=count("still_failing"), cases=changes,
        metrics=_metric_changes([before[i] for i in shared], [after[i] for i in shared]),
        categories=[CategoryChange(category=k, total=v[0], baseline_passed=v[1], candidate_passed=v[2])
                    for k, v in categories.items()],
        baseline_cost=_totals(base_costs, base_durations), candidate_cost=_totals(cand_costs, cand_durations),
    )
