"""The static demo is baked from stored results and published on a public website, so two things are tested hard:
that nothing machine-specific or secret-looking can get into it, and that what is baked fits together."""
import json
import uuid
from pathlib import Path

import pytest

from blackbox.agent.service import RunService
from blackbox.config import Settings
from blackbox.evals.cases import load_dataset
from blackbox.evals.runner import run_case
from blackbox.evals.scripts import reference_model
from blackbox.export_demo import (
    CURATED,
    MANIFEST,
    ExportError,
    build_demo,
    check_files,
    export_demo,
    note_run_ids,
    tour,
    write_files,
)
from blackbox.llm.base import ModelResponse
from blackbox.llm.scripted import ScriptedModel, scripted_model
from blackbox.models import EvalRunSummary, RunFault, RunRecord
from blackbox.publish_safety import audit, machine_identifiers, publishable, publishable_text
from blackbox.store.db import Store
from blackbox.telemetry.setup import Telemetry

GOLDEN = load_dataset()
LEAKED = r'File "<user-home>\Local Folder\Personal\agent-blackbox\backend\blackbox\agent\loop.py", line 12, in run'
WHEEL = r'File "<user-home>\Local Folder\Personal\agent-blackbox\.venv\Lib\site-packages\httpx\_client.py", line 3'
NO_NAMES: list[str] = []  # the audit rules, without whatever machine the tests happen to run on


# ---- rewriting machine-specific paths ------------------------------------------------------------------
def test_a_stack_trace_path_becomes_repository_relative():
    assert publishable_text(f"Traceback:\n  {LEAKED}\n    raise X") == (
        'Traceback:\n  File "backend/blackbox/agent/loop.py", line 12, in run\n    raise X')


def test_a_path_inside_the_virtual_environment_drops_the_environment_folders():
    assert publishable_text(WHEEL) == 'File "site-packages/httpx/_client.py", line 3'


def test_every_path_in_a_trace_is_rewritten_not_just_the_first():
    out = publishable_text(f"{LEAKED}\n{WHEEL}\n{LEAKED}")
    assert "<user-home>" not in out and out.count("File ") == 3


def test_text_without_a_placeholder_is_returned_untouched():
    text = 'File "backend/blackbox/agent/loop.py" and a note about C:/ drives is not rewritten here'
    assert publishable_text(text) is text


def test_rewriting_reaches_into_nested_values_and_does_not_mutate_the_input():
    data = {"a": [{"b": LEAKED}], "n": 3, "none": None, "ok": True}
    out = publishable(data)
    assert out["a"][0]["b"].startswith('File "backend/') and out["n"] == 3 and out["none"] is None
    assert "<user-home>" in data["a"][0]["b"]


def test_a_path_the_rewrite_does_not_understand_is_left_for_the_audit_to_catch():
    odd = r'File "<user-home>\AppData\Local\Programs\Python\Lib\json\decoder.py", line 1'
    assert audit(publishable(odd), NO_NAMES)


# ---- the audit ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    (r"File <user-home>\x.py", "placeholder"),
    (r"opened C:\Users\someone\notes.txt", "absolute file path"),
    ("opened d:/work/notes.txt", "absolute file path"),
    ("wrote /home/someone/notes.txt", "absolute file path"),
    ("wrote /Users/someone/notes.txt", "absolute file path"),
    ("write to someone@gmail.com please", "email"),
    ("token ghp_" + "a" * 36, "GitHub token"),
    ("token github_pat_" + "A1" * 20, "GitHub token"),
    ("key sk-" + "a1" * 15, "API key"),
    ("slack xoxb-1234567890-abcdefgh", "Slack token"),
    ("aws AKIA" + "ABCDEFGH12345678", "AWS key"),
    ("Authorization: Bearer " + "abcDEF123456" * 3, "bearer token"),
    ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.sig", "JWT"),
    ("-----BEGIN RSA PRIVATE KEY-----", "private key"),
])
def test_the_audit_catches_each_kind_of_leak(text, expected):
    found = audit({"x": [text]}, NO_NAMES)
    assert found and expected in found[0], found


@pytest.mark.parametrize("text", [
    "Order 42 arrived damaged, please refund it.",
    "My email is [REDACTED:email]",
    "contact support@example.com",
    "Support@EXAMPLE.COM",
    "trace 7c2d5c8d1d07d2aae844986da72ff8ae span 200fa5840e05c167",
    "Traceback (most recent call last):\n  File \"backend/blackbox/agent/loop.py\", line 3",
    "http://localhost:16686/trace/abc",
    "a time 12:30/13:45 and a ratio 3:/4",
    "sk-short",
    "",
])
def test_ordinary_text_passes_the_audit(text):
    assert audit({"x": text}, NO_NAMES) == []


def test_the_audit_looks_at_keys_and_deep_values_and_says_where():
    found = audit({"runs": [{"attributes": {"note": r"C:\Users\x\a.txt"}}], "me@gmail.com": 1}, NO_NAMES)
    assert any(f.startswith("$.runs[0].attributes.note:") for f in found)
    assert any("me@gmail.com" in f for f in found)


def test_this_machines_names_are_found_as_whole_words_only():
    assert audit({"x": "saved by Zebulon Quux"}, ["Quux"])
    assert audit({"x": "saved by quux"}, ["Quux"])            # case does not hide it
    assert audit({"x": "the Quuxville office"}, ["Quux"]) == []  # a longer word is not the name


def test_identifiers_are_the_account_the_home_folder_and_the_folders_between_it_and_the_repository():
    home = Path("/h/Alice Home")
    repo = home / "Local Stuff" / "Misc" / "agent-blackbox"
    assert machine_identifiers(home, repo, user="alice") == ["alice", "Alice Home", "Local Stuff", "Misc"]


def test_identifiers_leave_out_short_generic_and_project_names():
    home = Path("/home/runner")
    repo = home / "work" / "agent-blackbox" / "agent-blackbox"
    assert machine_identifiers(home, repo, user="runner") == ["runner"]
    assert machine_identifiers(Path("/x/ab"), Path("/y/agent-blackbox"), user="") == []


def test_the_audit_uses_this_machines_identifiers_when_none_are_given(monkeypatch):
    monkeypatch.setattr("blackbox.publish_safety.machine_identifiers", lambda: ["Quux"])
    assert audit({"x": "saved by quux"}) and audit({"x": "saved by nobody"}) == []


# ---- building the demo from a store -------------------------------------------------------------------
@pytest.fixture
def file_service(tmp_path):
    path = str(tmp_path / "demo.db")
    settings = Settings(db_path=path, otlp_endpoint=None)
    store = Store(path)
    telemetry = Telemetry(settings, store)
    yield RunService(settings, store, telemetry), path
    telemetry.shutdown()
    store.close()


def make_eval(service, passing, *, dataset=GOLDEN, kind="benchmark", variant="baseline", model="ollama:test"):
    summary = EvalRunSummary(
        eval_id=f"eval-{uuid.uuid4().hex[:8]}", kind=kind, model=model, dataset_version=dataset.version,
        dataset_hash=dataset.content_hash, seed=0, variant=variant, started_at="2026-10-19T00:00:00+00:00", status="running")
    service.store.create_eval_run(summary)
    for case_id, ok in passing.items():
        case = dataset.case(case_id)
        model_ = reference_model(case) if ok else ScriptedModel([ModelResponse(content="Sorry, no.")], name="wrong")
        service.store.save_eval_case(summary.eval_id, run_case(service, model_, case))
    service.store.finish_eval_run(summary.eval_id, "done", "2026-10-19T00:01:00+00:00")
    return summary.eval_id


@pytest.fixture
def two_evals(file_service):
    service, _ = file_service
    a = make_eval(service, {"N1": True, "N2": False})
    b = make_eval(service, {"N1": True, "N2": True})
    return service, a, b


def test_every_file_the_pages_need_is_built(two_evals):
    service, a, b = two_evals
    files = build_demo(service.store, [a, b])
    run_ids = [r["run_id"] for r in files["runs.json"]]
    assert len(run_ids) == 4
    for run_id in run_ids:
        assert files[f"spans/{run_id}.json"] and files[f"run-evaluations/{run_id}.json"]["stored"]
    assert {e["eval_id"] for e in files["evals.json"]} == {a, b}
    assert files[f"evals/{a}.json"]["cases"] and files["scenarios.json"] and files["faults.json"] == {}
    assert files["manifest.json"]["tour"] == {}  # these are not the curated evaluations
    assert files["manifest.json"]["counts"] == {"runs": 4, "spans": sum(len(files[f"spans/{r}.json"]) for r in run_ids),
                                                "evaluations": 2, "comparisons": 2, "refused_pairs": 2}


def test_a_comparison_is_baked_for_every_fair_pair_and_the_refusal_for_every_other(two_evals):
    service, a, b = two_evals
    files = build_demo(service.store, [a, b])
    index = files["comparisons/index.json"]
    assert set(index["ok"]) == {f"{a}|{b}", f"{b}|{a}"}
    assert index["refused"][f"{a}|{a}"] == "An evaluation cannot be compared with itself."
    baked = files[f"comparisons/{index['ok'][f'{a}|{b}']}"]
    assert (baked["fixed"], baked["broken"]) == (1, 0)


def test_an_unfair_pair_is_baked_as_the_same_plain_refusal_the_api_gives(file_service):
    service, _ = file_service
    a = make_eval(service, {"N1": True})
    other = make_eval(service, {"N1": True}, model="ollama:another")
    refusal = build_demo(service.store, [a, other])["comparisons/index.json"]["refused"][f"{a}|{other}"]
    assert "different models" in refusal


def test_only_the_chosen_evaluations_and_their_runs_are_exported(file_service):
    service, _ = file_service
    chosen = make_eval(service, {"N1": True})
    left_out = make_eval(service, {"N2": True})
    files = build_demo(service.store, [chosen])
    assert [e["eval_id"] for e in files["evals.json"]] == [chosen]
    runs = {r["run_id"] for r in files["runs.json"]}
    assert runs == {c["run_id"] for c in files[f"evals/{chosen}.json"]["cases"]}
    assert not runs & {c.run_id for c in service.store.get_eval_report(left_out).cases}


def test_scripted_example_runs_outside_any_evaluation_are_included_but_other_runs_are_not(file_service):
    service, _ = file_service
    chosen = make_eval(service, {"N1": True})
    example = service.run_sync(scripted_model("refund_happy_path"), "Refund order 42")
    stray = RunRecord(run_id="run-stray", task="a real-model run from an experiment", model="ollama:test", status="ok",
                      started_at="2026-10-18T00:00:00+00:00")
    service.store.create_run(stray)
    runs = {r["run_id"] for r in build_demo(service.store, [chosen])["runs.json"]}
    assert example.run_id in runs and stray.run_id not in runs


def test_a_run_shown_with_the_checks_of_the_exported_evaluation_not_of_one_that_was_left_out(file_service):
    service, _ = file_service
    chosen = make_eval(service, {"N1": True})
    case = service.store.get_eval_report(chosen).cases[0]
    # A later evaluation that is not exported judges the same run differently (what `rescore` does).
    later = make_eval(service, {"N2": True})
    service.store.save_eval_case(later, case.model_copy(update={"passed": False}))
    assert service.store.find_eval_case_for_run(case.run_id)[0] == later
    files = build_demo(service.store, [chosen])
    assert files[f"run-evaluations/{case.run_id}.json"]["eval_id"] == chosen


def test_a_missing_evaluation_is_an_error_not_a_smaller_demo(file_service):
    service, _ = file_service
    with pytest.raises(ExportError, match="eval-nope"):
        build_demo(service.store, ["eval-nope"])


def test_the_curated_list_has_no_duplicates_and_names_why_each_is_there():
    assert len(set(CURATED.values())) == len(CURATED) == 11
    assert all(label.strip() for label in CURATED)


def test_lab_runs_carry_their_planted_faults(file_service):
    service, _ = file_service
    chosen = make_eval(service, {"N1": True})
    run_id = service.store.get_eval_report(chosen).cases[0].run_id
    fault = RunFault(kind="tool_timeout", tool="check_refund_policy", description="the policy lookup times out", fired=True)
    service.store.save_run_faults(run_id, [fault])
    files = build_demo(service.store, [chosen])
    assert files["faults.json"] == {run_id: [fault.model_dump()]}


# ---- lab control runs and the tour ----------------------------------------------------------------------
def lab_note(service, control_id, faulted_id, fault="tool_timeout"):
    return {"kind": "faultlab", "fault": fault, "effect": "run_failed",
            "control": {"run_id": control_id}, "faulted": {"run_id": faulted_id}}


def test_note_run_ids_reads_both_sides_and_nothing_else():
    assert note_run_ids({"control": {"run_id": "run-a"}, "faulted": {"run_id": "run-b"}, "x": {"run_id": "run-c"}}) == ["run-a", "run-b"]
    assert note_run_ids(None) == [] and note_run_ids({}) == [] and note_run_ids({"control": "text", "faulted": {}}) == []


def test_a_lab_reports_control_run_is_exported_even_though_no_case_ran_it(file_service):
    service, _ = file_service
    # A real-model run that belongs to no evaluation, so it is not in the export as one of the scripted examples.
    service.store.create_run(RunRecord(run_id="run-control", task="control", model="ollama:test", status="ok", started_at="2026-10-18T00:00:00+00:00"))
    chosen = make_eval(service, {"N1": True})
    case = service.store.get_eval_report(chosen).cases[0]
    service.store.save_eval_case(chosen, case.model_copy(update={"case_id": "tool_timeout", "note": lab_note(service, "run-control", case.run_id)}))
    files = build_demo(service.store, [chosen])
    assert "run-control" in {r["run_id"] for r in files["runs.json"]}
    files["runs.json"] = [r for r in files["runs.json"] if r["run_id"] != "run-control"]
    with pytest.raises(ExportError, match="points at run run-control"):
        check_files(files)


def test_the_tour_points_at_the_failed_run_the_lab_and_the_two_comparisons():
    lab_b, lab_r = CURATED["failure lab: baseline"], CURATED["failure lab: resilient"]
    bench_b, bench_g = CURATED["benchmark golden-v3: baseline"], CURATED["benchmark golden-v3: guided v2"]

    class Case:
        def __init__(self, run_id, fault):
            self.run_id, self.note = run_id, {"fault": fault}

    class Report:
        cases = [Case("run-1", "wrong_tool"), Case("run-2", "tool_timeout")]

    bench_g3, hold = CURATED["benchmark golden-v3: guided v3"], CURATED["held-out holdout-v1: baseline"]
    assert tour({lab_b: Report, lab_r: Report, bench_b: Report, bench_g: Report, bench_g3: Report, hold: Report}) == {
        "failed_run": "run-2", "lab": lab_b, "fixed": [lab_b, lab_r], "regressed": [bench_b, bench_g],
        "second_attempt": [bench_b, bench_g3], "holdout": hold}
    assert "second_attempt" not in tour({lab_b: Report, bench_b: Report, bench_g: Report})
    assert tour({lab_b: Report}) == {"failed_run": "run-2"}  # without the resilient lab there is no "fixed" stop
    assert tour({}) == {}


def test_the_manifest_carries_the_tour(two_evals, monkeypatch):
    import blackbox.export_demo as module

    service, a, b = two_evals
    case = service.store.get_eval_report(a).cases[0]
    service.store.save_eval_case(a, case.model_copy(update={"case_id": "tool_timeout", "note": lab_note(service, case.run_id, case.run_id)}))
    for name, value in (("LAB_BASELINE", a), ("LAB_RESILIENT", b), ("BENCH_BASELINE", a), ("BENCH_GUIDED", b), ("BENCH_GUIDED_V3", b), ("HOLDOUT_BASELINE", a)):
        monkeypatch.setattr(module, name, value)
    manifest = build_demo(service.store, [a, b])[MANIFEST]
    assert manifest["tour"] == {"failed_run": case.run_id, "lab": a, "fixed": [a, b], "regressed": [a, b], "second_attempt": [a, b], "holdout": a}


def test_a_tour_pointing_at_something_that_was_not_exported_stops_the_export(two_evals):
    service, a, b = two_evals
    files = build_demo(service.store, [a, b])
    files[MANIFEST]["tour"] = {"failed_run": "run-ghost"}
    with pytest.raises(ExportError, match="tour points at run run-ghost"):
        check_files(files)
    files[MANIFEST]["tour"] = {"fixed": [a, "eval-ghost"]}
    with pytest.raises(ExportError, match="was not baked"):
        check_files(files)


# ---- the guards before anything is written ------------------------------------------------------------
def test_a_leaked_path_stops_the_export_and_nothing_is_written(two_evals, tmp_path):
    service, a, b = two_evals
    files = build_demo(service.store, [a, b])
    run_id = files["runs.json"][0]["run_id"]
    files[f"spans/{run_id}.json"][0]["attributes"]["note"] = r"C:\Users\someone\secret.txt"
    with pytest.raises(ExportError, match="absolute file path"):
        check_files(files)


def test_a_reference_to_a_run_that_was_not_exported_stops_the_export(two_evals):
    service, a, b = two_evals
    files = build_demo(service.store, [a, b])
    files["runs.json"].pop()
    with pytest.raises(ExportError, match="not exported"):
        check_files(files)


def test_an_evaluation_case_pointing_at_a_run_that_was_not_exported_stops_the_export(file_service):
    service, _ = file_service
    only = make_eval(service, {"N1": True})  # one evaluation: there is no comparison to notice the missing run instead
    files = build_demo(service.store, [only])
    assert files["comparisons/index.json"]["ok"] == {}
    files["runs.json"].clear()
    with pytest.raises(ExportError, match=f"{only} case N1 points at run"):
        check_files(files)


def test_a_run_without_its_spans_file_stops_the_export(two_evals):
    service, a, b = two_evals
    files = build_demo(service.store, [a, b])
    del files[f"spans/{files['runs.json'][0]['run_id']}.json"]
    with pytest.raises(ExportError, match="is missing"):
        check_files(files)


def test_a_comparison_pointing_at_an_unknown_run_stops_the_export(two_evals):
    service, a, b = two_evals
    files = build_demo(service.store, [a, b])
    name = next(n for n in files if n.startswith("comparisons/eval-"))
    files[name]["cases"][0]["candidate_run_id"] = "run-ghost"
    with pytest.raises(ExportError, match="run-ghost"):
        check_files(files)


def test_a_clean_build_passes_both_guards(two_evals):
    service, a, b = two_evals
    check_files(build_demo(service.store, [a, b]))


# ---- writing ------------------------------------------------------------------------------------------
def test_export_end_to_end_rewrites_stack_traces_and_leaves_the_database_alone(file_service, tmp_path):
    service, path = file_service
    chosen = make_eval(service, {"N1": True})
    span = service.store.get_spans(service.store.get_eval_report(chosen).cases[0].run_id)[0]
    service.store.upsert_spans([span.model_copy(update={"events": [{"name": "exception", "attributes": {"exception.stacktrace": LEAKED}}]})])
    before = Path(path).read_bytes()
    out = tmp_path / "demo-data"
    manifest = export_demo(path, out, [chosen])
    text = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*.json"))
    assert "<user-home>" not in text and "Local Folder" not in text
    assert "backend/blackbox/agent/loop.py" in text
    assert manifest["counts"]["evaluations"] == 1 and (out / MANIFEST).exists()
    assert Path(path).read_bytes() == before


def test_a_failed_check_writes_nothing(file_service, tmp_path, monkeypatch):
    service, path = file_service
    chosen = make_eval(service, {"N1": True})
    run_id = service.store.get_eval_report(chosen).cases[0].run_id
    span = service.store.get_spans(run_id)[0]
    service.store.upsert_spans([span.model_copy(update={"attributes": {"note": "write me at someone@gmail.com"}})])
    out = tmp_path / "demo-data"
    with pytest.raises(ExportError, match="email"):
        export_demo(path, out, [chosen])
    assert not out.exists()


def test_writing_replaces_an_earlier_export_but_refuses_a_folder_that_is_not_one(tmp_path):
    out = tmp_path / "demo-data"
    write_files({MANIFEST: {"v": 1}, "old.json": []}, out)
    write_files({MANIFEST: {"v": 2}}, out)
    assert not (out / "old.json").exists() and json.loads((out / MANIFEST).read_text(encoding="utf-8")) == {"v": 2}
    stranger = tmp_path / "mine"
    stranger.mkdir()
    (stranger / "notes.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(ExportError, match="not a demo export"):
        write_files({MANIFEST: {}}, stranger)
    assert (stranger / "notes.txt").read_text(encoding="utf-8") == "keep me"


def test_exporting_twice_gives_identical_bytes(file_service, tmp_path):
    service, path = file_service
    chosen = make_eval(service, {"N1": True, "N2": False})
    export_demo(path, tmp_path / "one", [chosen])
    export_demo(path, tmp_path / "two", [chosen])
    one = {p.relative_to(tmp_path / "one").as_posix(): p.read_bytes() for p in (tmp_path / "one").rglob("*.json")}
    two = {p.relative_to(tmp_path / "two").as_posix(): p.read_bytes() for p in (tmp_path / "two").rglob("*.json")}
    assert one == two and b"\r\n" not in b"".join(one.values())


def test_find_eval_case_for_run_can_be_limited_to_some_evaluations(file_service):
    service, _ = file_service
    first = make_eval(service, {"N1": True})
    case = service.store.get_eval_report(first).cases[0]
    second = make_eval(service, {"N2": True})
    service.store.save_eval_case(second, case)
    assert service.store.find_eval_case_for_run(case.run_id) == (second, "N1")
    assert service.store.find_eval_case_for_run(case.run_id, among={first}) == (first, "N1")
    assert service.store.find_eval_case_for_run(case.run_id, among={"eval-none"}) is None


# ---- the data that is actually committed --------------------------------------------------------------
DEMO_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demo-data"
# The numbers the README and the demo quote. They come from the stored evaluations; if the data is re-exported from
# a database where they changed, this fails and the documents need to change with it.
HEADLINE = {"eval-09d327ad": 19, "eval-b07a0e6d": 19, "eval-71224f4b": 16, "eval-c45fdf03": 17,
            "eval-286fe069": 5, "eval-ffb8d521": 5, "eval-dac487a9": 5}


def load_committed():
    return {p.relative_to(DEMO_DIR).as_posix(): json.loads(p.read_text(encoding="utf-8")) for p in DEMO_DIR.rglob("*.json")}


@pytest.fixture(scope="module")
def committed():
    if not DEMO_DIR.exists():
        pytest.skip("demo data has not been exported")
    return load_committed()


def test_the_committed_demo_data_has_nothing_to_hide_and_fits_together(committed):
    check_files(committed)  # the audit (with this machine's names too) and every reference between files


def test_the_committed_demo_data_holds_exactly_the_curated_evaluations(committed):
    assert sorted(e["eval_id"] for e in committed["evals.json"]) == sorted(CURATED.values())
    assert committed[MANIFEST]["evaluations"] and set(committed[MANIFEST]["evaluations"]) == set(CURATED.values())
    counts = committed[MANIFEST]["counts"]
    assert counts["runs"] == len(committed["runs.json"])
    assert counts["spans"] == sum(len(v) for k, v in committed.items() if k.startswith("spans/"))
    index = committed["comparisons/index.json"]
    assert counts["comparisons"] == len(index["ok"]) and counts["refused_pairs"] == len(index["refused"])
    assert len(index["ok"]) + len(index["refused"]) == len(CURATED) ** 2


def test_the_committed_headline_numbers_are_the_ones_the_documents_quote(committed):
    for eval_id, passed in HEADLINE.items():
        cases = committed[f"evals/{eval_id}.json"]["cases"]
        assert sum(1 for c in cases if c["passed"]) == passed, eval_id


def test_the_committed_baseline_against_resilient_comparison_says_nothing_was_broken_or_fixed(committed):
    index = committed["comparisons/index.json"]["ok"]
    result = committed[f"comparisons/{index['eval-09d327ad|eval-b07a0e6d']}"]
    assert (result["fixed"], result["broken"], result["matched"]) == (0, 0, 24)
    guided = committed[f"comparisons/{index['eval-09d327ad|eval-71224f4b']}"]
    assert (guided["fixed"], guided["broken"]) == (2, 5)


def test_the_committed_data_uses_unix_line_endings(committed):
    assert all(b"\r" not in p.read_bytes() for p in DEMO_DIR.rglob("*.json"))
