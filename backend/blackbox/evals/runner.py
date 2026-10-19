"""Runs a dataset (or the fault catalog) through the real agent and stores the evaluation.

Modes:
  ollama     the local model on every case             -> kind "benchmark"  (slow, real numbers)
  reference  a scripted correct run of every case      -> kind "reference"  (instant, proves the pipeline)
  faults     each planted fault through its base case  -> kind "validation" (instant, proves the checks)
  faultlab         infrastructure faults planted in one run, scripted model -> kind "faultlab" (instant)
  faultlab-ollama  the same, with the real model                          -> kind "faultlab" (a few minutes)

Every mode except `faults` takes an agent configuration (a variant), so the same cases can be run on the baseline
agent and on a fixed one and compared. `faults` always uses the baseline: it validates the checks, not an agent.
"""
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from blackbox.agent.config import AgentConfig
from blackbox.agent.service import RunService
from blackbox.evals.cases import Dataset, EvalCase
from blackbox.evals.checks import case_passed, evaluate_case
from blackbox.evals.faultlab import run_fault_lab
from blackbox.evals.scripts import FAULTS, Fault, Plant, reference_model
from blackbox.evals.trajectory import build_trajectory
from blackbox.faults.injector import FaultInjector
from blackbox.llm.base import ModelClient
from blackbox.llm.ollama_client import OllamaClient
from blackbox.llm.scripted import ScriptedModel
from blackbox.models import EvalCaseResult, EvalKind, EvalReport, EvalRunSummary
from blackbox.store.db import Store

Mode = Literal["ollama", "reference", "faults", "faultlab", "faultlab-ollama"]
KIND: dict[str, EvalKind] = {
    "ollama": "benchmark", "reference": "reference", "faults": "validation",
    "faultlab": "faultlab", "faultlab-ollama": "faultlab",
}
REAL_MODEL_MODES = ("ollama", "faultlab-ollama")
SEED = 0
Progress = Callable[[EvalCaseResult], None]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def run_case(service: RunService, model: ModelClient, case: EvalCase, *, max_steps: int | None = None,
             plant: Plant | None = None, note: dict | None = None, case_id: str | None = None,
             injector: FaultInjector | None = None, config: AgentConfig | None = None) -> EvalCaseResult:
    run = service.run_sync(model, case.task, max_steps, injector, config)
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
            "faults": "scripted:faults", "faultlab": "scripted:faultlab",
            "faultlab-ollama": f"ollama:{service.settings.ollama_model}"}[mode]


def prepare_evaluation(service: RunService, dataset: Dataset, mode: Mode, config: AgentConfig | None = None) -> EvalRunSummary:
    if config and config.name != "baseline" and mode == "faults":
        raise ValueError("the 'faults' mode validates the checks on scripted runs and always uses the baseline agent")
    summary = EvalRunSummary(
        eval_id=f"eval-{uuid.uuid4().hex[:8]}", kind=KIND[mode], model=_model_label(service, mode),
        dataset_version=dataset.version, dataset_hash=dataset.content_hash, seed=SEED if mode in REAL_MODEL_MODES else None,
        variant=config.name if config else "baseline", started_at=_now(), status="running",
    )
    service.store.create_eval_run(summary)
    return summary


def _fault_result(service: RunService, dataset: Dataset, fault: Fault) -> EvalCaseResult:
    base = dataset.case(fault.base_case)
    model = ScriptedModel(fault.script(base), name=fault.name)
    injector = FaultInjector(list(fault.inject)) if fault.inject else None
    result = run_case(service, model, base, max_steps=fault.max_steps, plant=fault.plant, case_id=fault.name,
                      injector=injector)
    failed = frozenset(c.metric for c in result.checks if c.passed is False)
    note = {"fault": fault.name, "description": fault.description, "base_case": fault.base_case,
            "expected_fail": sorted(fault.expect_fail), "actual_fail": sorted(failed), "matched": failed == fault.expect_fail}
    # For a validation batch, "passed" means the checks reacted exactly as expected.
    return result.model_copy(update={"category": "validation", "passed": failed == fault.expect_fail, "note": note})


def execute_evaluation(service: RunService, dataset: Dataset, mode: Mode, eval_id: str,
                       case_ids: list[str] | None = None, progress: Progress | None = None,
                       config: AgentConfig | None = None) -> None:
    store = service.store
    try:
        def real_model() -> ModelClient:
            return OllamaClient(service.settings.ollama_host, service.settings.ollama_model,
                                service.settings.ollama_timeout_s, seed=SEED)

        if mode == "faults":
            results = (_fault_result(service, dataset, f) for f in FAULTS)
        elif mode in ("faultlab", "faultlab-ollama"):
            reference = dataset.case("N1")
            results = run_fault_lab(service, dataset,
                                    real_model if mode == "faultlab-ollama" else lambda: reference_model(reference), config)
        else:
            wanted = [c for c in dataset.cases if not case_ids or c.id in case_ids]
            model_for: Callable[[EvalCase], ModelClient] = (
                (lambda c: OllamaClient(service.settings.ollama_host, service.settings.ollama_model,
                                        service.settings.ollama_timeout_s, seed=SEED))
                if mode == "ollama" else reference_model
            )
            results = (run_case(service, model_for(c), c, config=config) for c in wanted)
        for result in results:
            store.save_eval_case(eval_id, result)
            if progress:
                progress(result)
        store.finish_eval_run(eval_id, "done", _now())
    except Exception:
        store.finish_eval_run(eval_id, "error", _now())
        raise


def rescore_evaluation(store: Store, source: EvalReport, dataset: Dataset) -> str:
    """A new evaluation made by judging the stored runs of an existing one against another dataset version.

    No model is run: the agent's behaviour is exactly what was recorded, only the expectations change. It exists for
    the one legitimate reason to change expectations after seeing results, a correct answer the checks did not
    recognise (see the golden-v3 changelog). The old evaluation is kept under its own dataset hash, and the new one
    says where it came from.
    """
    if source.kind not in ("benchmark", "reference"):
        raise ValueError(f"only benchmark and reference evaluations can be rescored, not {source.kind}")
    known = {c.id: c for c in dataset.cases}
    missing = [c.case_id for c in source.cases if c.case_id not in known]
    if missing:
        raise ValueError(f"{dataset.version} has no case {', '.join(missing)}")
    changed = [c.case_id for c in source.cases if known[c.case_id].task != c.task]
    if changed:
        raise ValueError(f"the task of {', '.join(changed)} differs in {dataset.version}: those runs answered another task")
    summary = EvalRunSummary(
        eval_id=f"eval-{uuid.uuid4().hex[:8]}", kind=source.kind, model=source.model, dataset_version=dataset.version,
        dataset_hash=dataset.content_hash, seed=source.seed, variant=source.variant, rescored_from=source.eval_id,
        started_at=_now(), status="running",
    )
    store.create_eval_run(summary)
    try:
        for old in source.cases:
            run = store.get_run(old.run_id)
            if run is None:
                raise ValueError(f"run {old.run_id} of case {old.case_id} is not in the database")
            case = known[old.case_id]
            checks = evaluate_case(case, build_trajectory(run, store.get_spans(old.run_id)))
            store.save_eval_case(summary.eval_id, EvalCaseResult(
                case_id=case.id, category=case.category, task=case.task, run_id=run.run_id, run_status=run.status,
                passed=case_passed(checks), duration_ms=run.duration_ms, checks=checks))
        store.finish_eval_run(summary.eval_id, "done", _now())
    except Exception:
        store.finish_eval_run(summary.eval_id, "error", _now())
        raise
    return summary.eval_id


def run_evaluation(service: RunService, dataset: Dataset, mode: Mode, case_ids: list[str] | None = None,
                   progress: Progress | None = None, config: AgentConfig | None = None) -> str:
    summary = prepare_evaluation(service, dataset, mode, config)
    execute_evaluation(service, dataset, mode, summary.eval_id, case_ids, progress, config)
    return summary.eval_id
