"""Command line for evaluation batches.

  python -m blackbox.evals run --mode ollama                # real benchmark on the local model (minutes)
  python -m blackbox.evals run --mode ollama --cases N1,N4  # a few cases
  python -m blackbox.evals run --mode reference             # scripted correct run of every case
  python -m blackbox.evals run --mode faults                # planted faults: do the checks catch them?
  python -m blackbox.evals run --mode faultlab              # failure lab, scripted: where does analysis point?
  python -m blackbox.evals run --mode faultlab-ollama       # failure lab with the real model (a few minutes)
  python -m blackbox.evals run --mode ollama --variant full # the same benchmark on a fixed agent
  python -m blackbox.evals compare eval-aaaa eval-bbbb      # before/after of two stored evaluations

Run from ./backend. Results go to the same SQLite database the API reads (BLACKBOX_DB_PATH).
"""
import argparse
import sys
import time

from blackbox.agent.config import PRESETS, preset
from blackbox.agent.service import RunService
from blackbox.config import get_settings
from blackbox.evals.cases import load_dataset
from blackbox.evals.compare import ComparisonError, compare
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


def _seconds(ms: float | None) -> str:
    return "-" if ms is None else f"{ms / 1000:.1f}s"


def _compare(baseline_id: str, candidate_id: str) -> None:
    settings = get_settings()
    store = Store(settings.db_path)
    try:
        reports = [store.get_eval_report(i) for i in (baseline_id, candidate_id)]
        for eval_id, report in zip((baseline_id, candidate_id), reports):
            if report is None:
                sys.exit(f"No evaluation {eval_id!r} in {settings.db_path}")
        try:
            result = compare(store, reports[0], reports[1])  # type: ignore[arg-type]
        except ComparisonError as exc:
            sys.exit(f"Cannot compare: {exc}")
    finally:
        store.close()
    b, c = result.baseline, result.candidate
    print(f"{result.kind}: {b.eval_id} [{b.variant}] -> {c.eval_id} [{c.variant}]   {b.model}, {b.dataset_version} ({b.dataset_hash})")
    print(f"  {result.matched} cases in both: {result.fixed} fixed, {result.broken} broken, "
          f"{result.still_passing} still passing, {result.still_failing} still failing")
    for case in result.cases:
        if case.change in ("still_passing",):
            continue
        what = (f"{case.baseline_effect} -> {case.candidate_effect}" if result.kind == "faultlab"
                else f"failed: {', '.join(case.candidate_failed_checks) or '-'}")
        print(f"    {case.change.upper().replace('_', ' '):<14} {case.case_id:<18} {what}")
    print("  checks (passed/total, baseline -> candidate)")
    for m in result.metrics:
        print(f"    {m.metric:<22} {m.baseline_passed:>2}/{m.baseline_total:<2} -> {m.candidate_passed:>2}/{m.candidate_total:<2}"
              f"{'  (gating)' if m.gating else ''}")
    bc, cc = result.baseline_cost, result.candidate_cost
    print("  cost over the matched cases (baseline -> candidate)")
    print(f"    tool calls   {bc.tool_calls} -> {cc.tool_calls}    model calls {bc.model_calls} -> {cc.model_calls}    retries {bc.retries} -> {cc.retries}")
    print(f"    median run   {_seconds(bc.median_duration_ms)} -> {_seconds(cc.median_duration_ms)}    total {_seconds(bc.total_duration_ms)} -> {_seconds(cc.total_duration_ms)}")
    if bc.input_tokens is not None and cc.input_tokens is not None:
        print(f"    tokens in    {bc.input_tokens} -> {cc.input_tokens}    out {bc.output_tokens} -> {cc.output_tokens}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m blackbox.evals")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run an evaluation batch")
    run.add_argument("--mode", choices=["ollama", "reference", "faults", "faultlab", "faultlab-ollama"], required=True)
    run.add_argument("--dataset", default="golden-v2")
    run.add_argument("--cases", help="comma-separated case ids (default: all)")
    run.add_argument("--variant", choices=list(PRESETS), default="baseline", help="agent configuration (default: baseline)")
    cmp = sub.add_parser("compare", help="before/after of two stored evaluations")
    cmp.add_argument("baseline")
    cmp.add_argument("candidate")
    args = parser.parse_args(argv)

    if args.command == "compare":
        return _compare(args.baseline, args.candidate)

    settings = get_settings()
    dataset = load_dataset(args.dataset)
    config = preset(args.variant)
    if args.mode == "faults" and config.name != "baseline":
        sys.exit("--mode faults validates the checks and always uses the baseline agent; drop --variant.")
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

    print(f"{args.mode} [{config.name}] on {dataset.version} ({dataset.content_hash}), {len(case_ids or dataset.cases)} cases")
    eval_id = run_evaluation(service, dataset, args.mode, case_ids, progress, config)
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
