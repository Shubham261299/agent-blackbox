"""Runs a dataset (or the fault catalog) through the real agent and stores the evaluation.

Modes:
  ollama     the local model on every case             -> kind "benchmark"  (slow, real numbers)
  reference  a scripted correct run of every case      -> kind "reference"  (instant, proves the pipeline)
  faults     each planted fault through its base case  -> kind "validation" (instant, proves the checks)
"""
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from blackbox.agent.service import RunService
from blackbox.evals.cases import Dataset, EvalCase
from blackbox.evals.checks import case_passed, evaluate_case
from blackbox.evals.scripts import FAULTS, Fault, Plant, reference_model
from blackbox.evals.trajectory import build_trajectory
from blackbox.llm.base import ModelClient
from blackbox.llm.ollama_client import OllamaClient
from blackbox.llm.scripted import ScriptedModel
from blackbox.models import EvalCaseResult, EvalKind, EvalRunSummary

Mode = Literal["ollama", "reference", "faults"]
KIND: dict[str, EvalKind] = {"ollama": "benchmark", "reference": "reference", "faults": "validation"}
SEED = 0
Progress = Callable[[EvalCaseResult], None]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def run_case(service: RunService, model: ModelClient, case: EvalCase, *, max_steps: int | None = None,
             plant: Plant | None = None, note: dict | None = None, case_id: str | None = None) -> EvalCaseResult:
    run = service.run_sync(model, case.task, max_steps)
    if plant:
        plant(service.store, run.run_id)
    traj = build_trajectory(run, service.store.get_spans(run.run_id))
    checks = evaluate_case(case, traj)
    return EvalCaseResult(
        case_id=case_id or case.id, category=case.category, task=case.task, run_id=run.run_id,
        run_status=run.status, passed=case_passed(checks), duration_ms=run.duration_ms, note=note, checks=checks,
    )


def _model_label(service: RunService, mode: Mode) -> str:
    return {"ollama": f"ollama:{service.settings.ollama_model}", "reference": "scripted:reference",
            "faults": "scripted:faults"}[mode]


def prepare_evaluation(service: RunService, dataset: Dataset, mode: Mode) -> EvalRunSummary:
    summary = EvalRunSummary(
        eval_id=f"eval-{uuid.uuid4().hex[:8]}", kind=KIND[mode], model=_model_label(service, mode),
        dataset_version=dataset.version, dataset_hash=dataset.content_hash, seed=SEED if mode == "ollama" else None,
        started_at=_now(), status="running",
    )
    service.store.create_eval_run(summary)
    return summary


def _fault_result(service: RunService, dataset: Dataset, fault: Fault) -> EvalCaseResult:
    base = dataset.case(fault.base_case)
    model = ScriptedModel(fault.script(base), name=fault.name)
    result = run_case(service, model, base, max_steps=fault.max_steps, plant=fault.plant, case_id=fault.name)
    failed = frozenset(c.metric for c in result.checks if c.passed is False)
    note = {"fault": fault.name, "description": fault.description, "base_case": fault.base_case,
            "expected_fail": sorted(fault.expect_fail), "actual_fail": sorted(failed), "matched": failed == fault.expect_fail}
    # For a validation batch, "passed" means the checks reacted exactly as expected.
    return result.model_copy(update={"category": "validation", "passed": failed == fault.expect_fail, "note": note})


def execute_evaluation(service: RunService, dataset: Dataset, mode: Mode, eval_id: str,
                       case_ids: list[str] | None = None, progress: Progress | None = None) -> None:
    store = service.store
    try:
        if mode == "faults":
            results = (_fault_result(service, dataset, f) for f in FAULTS)
        else:
            wanted = [c for c in dataset.cases if not case_ids or c.id in case_ids]
            model_for: Callable[[EvalCase], ModelClient] = (
                (lambda c: OllamaClient(service.settings.ollama_host, service.settings.ollama_model,
                                        service.settings.ollama_timeout_s, seed=SEED))
                if mode == "ollama" else reference_model
            )
            results = (run_case(service, model_for(c), c) for c in wanted)
        for result in results:
            store.save_eval_case(eval_id, result)
            if progress:
                progress(result)
        store.finish_eval_run(eval_id, "done", _now())
    except Exception:
        store.finish_eval_run(eval_id, "error", _now())
        raise


def run_evaluation(service: RunService, dataset: Dataset, mode: Mode, case_ids: list[str] | None = None,
                   progress: Progress | None = None) -> str:
    summary = prepare_evaluation(service, dataset, mode)
    execute_evaluation(service, dataset, mode, summary.eval_id, case_ids, progress)
    return summary.eval_id
