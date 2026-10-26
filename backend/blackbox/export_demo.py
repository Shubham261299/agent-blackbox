"""Bakes a small, curated part of the stored results into JSON files for the static demo website.

    python -m blackbox.export_demo                 # writes frontend/public/demo-data/ from the local database

The files are what the API would answer (same store, same `compare`, same trace analysis), so the demo shows what
the live app shows. Two guards run before anything is written: every string is made publishable (machine-specific
paths in stack traces become repository-relative) and then audited, and every reference between files is checked.
The stored database is only read.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from blackbox.config import DEFAULT_DB_PATH, REPO_ROOT
from blackbox.evals.compare import ComparisonError, compare
from blackbox.evals.run_evaluation import build_run_evaluation
from blackbox.llm.scripted import SCENARIO_INFO
from blackbox.models import RunRecord, ScenarioInfo
from blackbox.publish_safety import audit, publishable
from blackbox.store.db import Store

DEFAULT_OUT = REPO_ROOT / "frontend" / "public" / "demo-data"
MANIFEST = "manifest.json"
FORMAT = 1

# The evaluations the demo holds, chosen so a visitor sees the whole story and not 31 evaluations of mostly repeats:
# the headline benchmark with every variant that matters, the held-out set, the failure lab, and the two ways the
# checks themselves are tested. The `full` variants give the same results as `guided` and are left out on purpose.
CURATED = {
    "benchmark golden-v3: baseline": "eval-09d327ad",
    "benchmark golden-v3: resilient": "eval-b07a0e6d",
    "benchmark golden-v3: guided v2": "eval-71224f4b",
    "benchmark golden-v3: guided v3": "eval-c45fdf03",
    "held-out holdout-v1: baseline": "eval-286fe069",
    "held-out holdout-v1: resilient": "eval-ffb8d521",
    "held-out holdout-v1: guided v3": "eval-dac487a9",
    "failure lab: baseline": "eval-7f1699f1",
    "failure lab: resilient": "eval-0f9152b9",
    "reference (the checks accept a known-good run)": "eval-60b97115",
    "validation (the checks catch planted faults)": "eval-a5479ac6",
}


# The four stops of the "Start here" card, as ids the pages can link to. They are looked up from the data, not typed in
# by hand, so a re-export that changes them changes the card.
TOUR_FAULT = "tool_timeout"
LAB_BASELINE, LAB_RESILIENT = CURATED["failure lab: baseline"], CURATED["failure lab: resilient"]
BENCH_BASELINE, BENCH_GUIDED = CURATED["benchmark golden-v3: baseline"], CURATED["benchmark golden-v3: guided v2"]
BENCH_GUIDED_V3 = CURATED["benchmark golden-v3: guided v3"]
HOLDOUT_BASELINE = CURATED["held-out holdout-v1: baseline"]


class ExportError(RuntimeError):
    """The export found something it must not publish, or its own files do not fit together."""


def note_run_ids(note: dict[str, Any] | None) -> list[str]:
    """The runs a failure-lab case names besides its own: the untouched control run and the faulted one."""
    return [side["run_id"] for key in ("control", "faulted") if isinstance(side := (note or {}).get(key), dict) and "run_id" in side]


def _runs_of(store: Store, eval_ids: list[str]) -> list[RunRecord]:
    wanted: set[str] = set()
    for eval_id in eval_ids:
        report = store.get_eval_report(eval_id)
        for case in report.cases:  # type: ignore[union-attr]
            wanted.add(case.run_id)
            wanted.update(note_run_ids(case.note))  # a lab report links to its control run
    everything = store.list_runs(100_000)  # newest first, which is the order the app shows them in
    # The scripted example runs from the original scenarios (not part of any evaluation) keep the run list from
    # being nothing but benchmark cases.
    examples = {r.run_id for r in everything
                if r.model.startswith("scripted:") and store.find_eval_case_for_run(r.run_id) is None}
    return [r for r in everything if r.run_id in wanted | examples]


def build_demo(store: Store, eval_ids: list[str]) -> dict[str, Any]:
    """Every file of the demo as {relative path: JSON-compatible value}. Reads the store, writes nothing."""
    missing = [e for e in eval_ids if store.get_eval_report(e) is None]
    if missing:
        raise ExportError(f"evaluations not in the database: {', '.join(missing)}")
    reports = {e: store.get_eval_report(e) for e in eval_ids}
    runs = _runs_of(store, eval_ids)
    files: dict[str, Any] = {}

    files["scenarios.json"] = [ScenarioInfo(name=n, description=d, example_task=t).model_dump()
                               for n, (d, t) in SCENARIO_INFO.items()]
    files["runs.json"] = [r.model_dump() for r in runs]
    faults: dict[str, Any] = {}
    span_count = 0
    for run in runs:
        spans = store.get_spans(run.run_id)
        span_count += len(spans)
        files[f"spans/{run.run_id}.json"] = [s.model_dump() for s in spans]
        found = store.find_eval_case_for_run(run.run_id, among=set(eval_ids))
        files[f"run-evaluations/{run.run_id}.json"] = build_run_evaluation(store, run, found).model_dump()
        run_faults = store.get_run_faults(run.run_id)
        if run_faults:
            faults[run.run_id] = [f.model_dump() for f in run_faults]
    files["faults.json"] = faults

    summaries = [s for s in store.list_eval_runs(100_000) if s.eval_id in reports]  # newest first, like the app
    files["evals.json"] = [s.model_dump() for s in summaries]
    for eval_id, report in reports.items():
        files[f"evals/{eval_id}.json"] = report.model_dump()  # type: ignore[union-attr]

    ok: dict[str, str] = {}
    refused: dict[str, str] = {}
    for baseline in eval_ids:
        for candidate in eval_ids:
            key = f"{baseline}|{candidate}"
            try:
                result = compare(store, reports[baseline], reports[candidate])  # type: ignore[arg-type]
            except ComparisonError as exc:
                refused[key] = str(exc)
                continue
            ok[key] = f"{baseline}__{candidate}.json"
            files[f"comparisons/{ok[key]}"] = result.model_dump()
    files["comparisons/index.json"] = {"ok": ok, "refused": refused}

    recorded = sorted(r.started_at[:10] for r in runs if r.model.startswith("ollama:"))
    models = sorted({s.model for s in summaries if s.model.startswith("ollama:")})
    files[MANIFEST] = {
        "format": FORMAT,
        "models": models,
        "recorded_from": recorded[0] if recorded else None,
        "recorded_to": recorded[-1] if recorded else None,
        "counts": {"runs": len(runs), "spans": span_count, "evaluations": len(summaries),
                   "comparisons": len(ok), "refused_pairs": len(refused)},
        "evaluations": [s.eval_id for s in summaries],
        "tour": tour(reports),
    }
    return files


def tour(reports: dict[str, Any]) -> dict[str, Any]:
    """Where the four stops of the landing card go. Empty for a smaller export that does not hold the lab."""
    lab = reports.get(LAB_BASELINE)
    failed = next((c.run_id for c in lab.cases if (c.note or {}).get("fault") == TOUR_FAULT), None) if lab else None
    out: dict[str, Any] = {}
    if failed:
        out["failed_run"] = failed
    if lab and LAB_RESILIENT in reports:
        out["lab"] = LAB_BASELINE
        out["fixed"] = [LAB_BASELINE, LAB_RESILIENT]
    if BENCH_BASELINE in reports and BENCH_GUIDED in reports:
        out["regressed"] = [BENCH_BASELINE, BENCH_GUIDED]
    if BENCH_BASELINE in reports and BENCH_GUIDED_V3 in reports:
        out["second_attempt"] = [BENCH_BASELINE, BENCH_GUIDED_V3]
    if HOLDOUT_BASELINE in reports:
        out["holdout"] = HOLDOUT_BASELINE
    return out


def check_files(files: dict[str, Any]) -> None:
    """Publishable and consistent, or an ExportError saying what is not. Nothing is written before this passes."""
    problems = audit(files)
    run_ids = {r["run_id"] for r in files["runs.json"]}
    eval_ids = {e["eval_id"] for e in files["evals.json"]}
    for eval_id in eval_ids:
        for case in files[f"evals/{eval_id}.json"]["cases"]:
            for run_id in [case["run_id"], *note_run_ids(case.get("note"))]:
                if run_id not in run_ids:
                    problems.append(f"{eval_id} case {case['case_id']} points at run {run_id}, which is not exported")
    for name, comparison in ((n, v) for n, v in files.items() if n.startswith("comparisons/") and n != "comparisons/index.json"):
        for case in comparison["cases"]:
            for run_id in (case["baseline_run_id"], case["candidate_run_id"]):
                if run_id not in run_ids:
                    problems.append(f"{name} case {case['case_id']} points at run {run_id}, which is not exported")
    tour_runs = [files[MANIFEST]["tour"].get("failed_run")]
    for run_id in (r for r in tour_runs if r):
        if run_id not in run_ids:
            problems.append(f"the tour points at run {run_id}, which is not exported")
    holdout = files[MANIFEST]["tour"].get("holdout")
    if holdout and holdout not in eval_ids:
        problems.append(f"the tour points at the evaluation {holdout}, which is not exported")
    for pair in (files[MANIFEST]["tour"].get(k) for k in ("fixed", "regressed", "second_attempt")):
        if pair and f"{pair[0]}|{pair[1]}" not in files["comparisons/index.json"]["ok"]:
            problems.append(f"the tour points at the comparison {pair[0]} against {pair[1]}, which was not baked")
    for run_id in run_ids:
        for needed in (f"spans/{run_id}.json", f"run-evaluations/{run_id}.json"):
            if needed not in files:
                problems.append(f"{needed} is missing")
    if problems:
        shown = "\n  ".join(problems[:25])
        more = f"\n  ... and {len(problems) - 25} more" if len(problems) > 25 else ""
        raise ExportError(f"not publishing: {len(problems)} problem(s)\n  {shown}{more}")


def write_files(files: dict[str, Any], out: Path) -> None:
    """Replace `out` with the files. Refuses a folder that is not an earlier export (it would delete someone's files)."""
    if out.exists() and any(out.iterdir()) and not (out / MANIFEST).exists():
        raise ExportError(f"{out} exists and is not a demo export; refusing to overwrite it")
    if out.exists():
        shutil.rmtree(out)
    for name, value in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Compact and key-sorted so a re-export of the same results is byte-identical and the diff shows real changes.
        path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def export_demo(db_path: str = DEFAULT_DB_PATH, out: Path = DEFAULT_OUT, eval_ids: list[str] | None = None) -> dict[str, Any]:
    store = Store(db_path)
    try:
        files = publishable(build_demo(store, eval_ids or list(CURATED.values())))
    finally:
        store.close()
    check_files(files)
    write_files(files, out)
    return files[MANIFEST]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m blackbox.export_demo", description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="the database to read (default: the local one)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="the folder to write (default: frontend/public/demo-data)")
    args = parser.parse_args(argv)
    try:
        manifest = export_demo(args.db, args.out)
    except ExportError as exc:
        print(exc, file=sys.stderr)
        return 1
    c = manifest["counts"]
    print(f"wrote {args.out}: {c['runs']} runs, {c['spans']} spans, {c['evaluations']} evaluations, "
          f"{c['comparisons']} comparisons ({c['refused_pairs']} refused pairs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
