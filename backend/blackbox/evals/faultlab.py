"""The failure lab: plant a known failure in the refund task, then ask trace analysis where to look.

For each fault the lab runs the same task twice with the same model, once untouched (control) and once with the
fault planted, evaluates both from their stored traces, and scores the localizer against the span the injector
recorded as the origin. The localizer is never told which fault was planted.
"""
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from blackbox.agent.config import AgentConfig
from blackbox.agent.service import RunService
from blackbox.evals.cases import Dataset, EvalCase
from blackbox.evals.checks import case_passed, evaluate_case
from blackbox.evals.localize import locate
from blackbox.evals.trajectory import Trajectory, build_trajectory
from blackbox.faults.injector import FaultInjector, FaultSpec
from blackbox.llm.base import ModelClient
from blackbox.models import CheckResult, EvalCaseResult, RunRecord

BASE_CASE = "N1"  # "Order 42 arrived damaged, please refund it." lookup, check policy, refund


@dataclass(frozen=True)
class LabFault:
    name: str
    title: str
    description: str
    spec: FaultSpec


LAB_FAULTS: list[LabFault] = [
    LabFault(
        "tool_timeout", "Tool timeout",
        "The policy check does not answer in time. The baseline agent does not handle infrastructure failures, so the run ends.",
        FaultSpec("tool_timeout", tool="check_refund_policy", params={"delay_s": 0.3}),
    ),
    LabFault(
        "malformed_output", "Malformed tool output",
        "The order lookup returns an error web page instead of an order. The call still counts as a success, so nothing raises.",
        FaultSpec("malformed_output", tool="lookup_order", params={"mode": "html"}),
    ),
    LabFault(
        "wrong_tool", "Wrong tool chosen",
        "The model's first move is swapped for an address change on an order that was never looked up.",
        FaultSpec("wrong_tool", params={"to_tool": "update_shipping_address", "args": {"order_id": 42, "new_address": "9 Elm Road"}}),
    ),
    LabFault(
        "model_error", "Model call fails",
        "The model backend stops answering after the lookup, as an unreachable Ollama would.",
        FaultSpec("model_error", occurrence=2),
    ),
]

SUSPECTS_SHOWN = 5


def _summary(run: RunRecord, traj: Trajectory, checks: list[CheckResult]) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "run_status": run.status,
        "gating_passed": case_passed(checks),
        "failed_checks": [c.metric for c in checks if c.passed is False],
        "duration_ms": run.duration_ms,
        "tool_calls": len(traj.tool_calls),
        "answer": run.final_answer,
    }


def effect_of(faulted: dict[str, Any]) -> str:
    """What the fault did to the run, in one word the UI turns into a sentence."""
    if faulted["run_status"] == "error":
        return "run_failed"
    if not faulted["gating_passed"]:
        return "gating_failed"
    if faulted["failed_checks"]:
        return "silent"  # both gating checks passed; only a reported check noticed
    return "no_effect"


def _evaluate(service: RunService, run: RunRecord, case: EvalCase) -> tuple[Trajectory, list[CheckResult]]:
    traj = build_trajectory(run, service.store.get_spans(run.run_id))
    return traj, evaluate_case(case, traj)


def _warm_up(model: ModelClient) -> None:
    """Load a real model into memory before anything is timed, so the control run is not charged for the load
    (it made faulted runs look faster than the control). Not traced and not stored: it belongs to no run."""
    if model.provider != "ollama":
        return
    try:
        model.chat([{"role": "user", "content": "Reply with the single word: ready"}], [])
    except Exception:
        pass  # the runs that follow record the failure properly


def run_fault_lab(service: RunService, dataset: Dataset, new_model: Callable[[], ModelClient],
                  config: AgentConfig | None = None) -> Iterator[EvalCaseResult]:
    case = dataset.case(BASE_CASE)
    _warm_up(new_model())
    control_run = service.run_sync(new_model(), case.task, config=config)
    control_traj, control_checks = _evaluate(service, control_run, case)
    control = _summary(control_run, control_traj, control_checks)

    for lab in LAB_FAULTS:
        injector = FaultInjector([lab.spec])
        run = service.run_sync(new_model(), case.task, injector=injector, config=config)
        traj, checks = _evaluate(service, run, case)
        suspects = locate(traj, checks)
        origin = injector.faults[0].origin_span_id
        ids = [s.span_id for s in suspects]
        rank = ids.index(origin) + 1 if origin in ids else None
        names = {s.span_id: s.name for s in traj.spans}
        faulted = _summary(run, traj, checks)
        note = {
            "kind": "faultlab", "fault": lab.name, "title": lab.title, "description": lab.description,
            "injected": lab.spec.describe(), "fired": injector.faults[0].fired,
            "origin_span_id": origin, "origin_span_name": names.get(origin) if origin else None,
            "suspects": [s.model_dump() for s in suspects[:SUSPECTS_SHOWN]],
            "rank": rank, "hit_at_1": rank == 1, "hit_at_3": rank is not None and rank <= 3,
            "control": control, "faulted": faulted, "effect": effect_of(faulted),
        }
        yield EvalCaseResult(
            case_id=lab.name, category="faultlab", task=case.task, run_id=run.run_id, run_status=run.status,
            passed=rank == 1, duration_ms=run.duration_ms, note=note, checks=checks,
        )
