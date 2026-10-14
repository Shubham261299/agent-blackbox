"""Command line for evaluation batches.

  python -m blackbox.evals run --mode ollama                # real benchmark on the local model (minutes)
  python -m blackbox.evals run --mode ollama --cases N1,N4  # a few cases
  python -m blackbox.evals run --mode reference             # scripted correct run of every case
  python -m blackbox.evals run --mode faults                # planted faults: do the checks catch them?
  python -m blackbox.evals run --mode faultlab              # failure lab, scripted: where does analysis point?
  python -m blackbox.evals run --mode faultlab-ollama       # failure lab with the real model (a few minutes)

Run from ./backend. Results go to the same SQLite database the API reads (BLACKBOX_DB_PATH).
"""
import argparse
import sys
import time

from blackbox.agent.service import RunService
from blackbox.config import get_settings
from blackbox.evals.cases import load_dataset
from blackbox.evals.runner import run_evaluation
from blackbox.models import EvalCaseResult
from blackbox.store.db import Store
from blackbox.telemetry.setup import Telemetry


def _check_ollama(host: str, model: str) -> None:
    import ollama

    try:
        names = {m.model for m in ollama.Client(host=host, timeout=5).list().models}
    except Exception as exc:
        sys.exit(f"Cannot reach Ollama at {host}: {exc}\nStart it, or use --mode reference. No hosted model is ever used.")
    if model not in names and f"{model}:latest" not in names:
        sys.exit(f"Ollama has no model {model!r}. Installed: {', '.join(sorted(names)) or 'none'}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m blackbox.evals")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run an evaluation batch")
    run.add_argument("--mode", choices=["ollama", "reference", "faults", "faultlab", "faultlab-ollama"], required=True)
    run.add_argument("--dataset", default="golden-v2")
    run.add_argument("--cases", help="comma-separated case ids (default: all)")
    args = parser.parse_args(argv)

    settings = get_settings()
    dataset = load_dataset(args.dataset)
    if args.mode in ("ollama", "faultlab-ollama"):
        _check_ollama(settings.ollama_host, settings.ollama_model)

    store = Store(settings.db_path)
    telemetry = Telemetry(settings, store)
    service = RunService(settings, store, telemetry)
    case_ids = [c.strip() for c in args.cases.split(",")] if args.cases else None
    unknown = set(case_ids or []) - {c.id for c in dataset.cases}
    if unknown:
        sys.exit(f"Unknown case ids: {', '.join(sorted(unknown))}")

    started = time.perf_counter()

    def progress(result: EvalCaseResult) -> None:
        note = result.note or {}
        if note.get("kind") == "faultlab":
            print(f"  {'LOCATED' if note['hit_at_1'] else 'MISSED '} {result.case_id:<18} "
                  f"suspect rank {note['rank'] or '-'}  effect: {note['effect']}", flush=True)
            return
        mark = "PASS" if result.passed else "FAIL"
        failed = [c.metric for c in result.checks if c.passed is False]
        took = f"{(result.duration_ms or 0) / 1000:.1f}s"
        print(f"  {mark}  {result.case_id:<26} {took:>7}  {', '.join(failed) if failed else ''}", flush=True)

    print(f"{args.mode} on {dataset.version} ({dataset.content_hash}), {len(case_ids or dataset.cases)} cases")
    eval_id = run_evaluation(service, dataset, args.mode, case_ids, progress)
    report = store.get_eval_report(eval_id)
    assert report is not None
    print(f"\n{eval_id}: {report.n_passed}/{report.n_cases} passed in {time.perf_counter() - started:.0f}s")
    for m in report.metrics:
        if m.total:
            print(f"  {m.metric:<22} {m.passed:>2}/{m.total:<2} {'(gating)' if m.gating else ''}")
    telemetry.shutdown()
    store.close()


if __name__ == "__main__":
    main()
