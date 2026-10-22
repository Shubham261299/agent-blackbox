"""The checks and suspects for one run, shared by the API and the static demo export so both show the same thing."""
from blackbox.evals.checks import evaluate_generic
from blackbox.evals.localize import locate
from blackbox.evals.trajectory import build_trajectory
from blackbox.models import RunEvaluation, RunRecord
from blackbox.store.db import Store


def build_run_evaluation(store: Store, run: RunRecord, found: tuple[str, str] | None) -> RunEvaluation:
    """`found` is the (eval id, case id) the run belonged to, or None: then only the checks that need no
    expectations are computed on the fly and the evaluation is marked as not stored."""
    traj = build_trajectory(run, store.get_spans(run.run_id))
    if found:
        eval_id, case_id = found
        checks = store.get_case_checks(eval_id, case_id)
        return RunEvaluation(run_id=run.run_id, eval_id=eval_id, case_id=case_id, stored=True, checks=checks,
                             suspects=locate(traj, checks))
    checks = evaluate_generic(traj)
    return RunEvaluation(run_id=run.run_id, stored=False, checks=checks, suspects=locate(traj, checks))
