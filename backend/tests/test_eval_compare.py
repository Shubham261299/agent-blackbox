"""Before/after comparison: variant plumbing, fixed / broken counting, the refusals that keep a comparison fair,
the CLI and the API. Evaluations are built from real scripted runs so cost and run links are real too."""
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from blackbox.agent.config import preset
from blackbox.api.main import create_app
from blackbox.evals.__main__ import main as cli_main
from blackbox.evals.cases import load_dataset
from blackbox.evals.compare import ComparisonError, compare
from blackbox.evals.localize import locate
from blackbox.evals.runner import run_case, run_evaluation
from blackbox.evals.scripts import reference_model
from blackbox.faults.injector import FaultInjector, FaultSpec
from blackbox.llm.base import ModelResponse
from blackbox.llm.scripted import ScriptedModel
from blackbox.models import EvalRunSummary
from blackbox.store.db import Store

GOLDEN = load_dataset()
HOLDOUT = load_dataset("holdout-v1")
CASES = ["N1", "N2", "A1", "W1"]
TIMEOUT = FaultSpec("tool_timeout", tool="check_refund_policy", params={"delay_s": 0.01})


def build_eval(service, passing, *, config=None, dataset=GOLDEN, kind="benchmark", model="scripted:test", status="done",
               seed=None, injectors=None):
    """Store an evaluation whose cases pass or fail as told: a failing case gets an answer that skips the task."""
    summary = EvalRunSummary(
        eval_id=f"eval-{uuid.uuid4().hex[:8]}", kind=kind, model=model, dataset_version=dataset.version,
        dataset_hash=dataset.content_hash, seed=seed, variant=config.name if config else "baseline",
        started_at="2026-10-19T00:00:00+00:00", status="running")
    service.store.create_eval_run(summary)
    for case_id, ok in passing.items():
        case = dataset.case(case_id)
        model_ = reference_model(case) if ok else ScriptedModel([ModelResponse(content="Sorry, no.")], name="wrong")
        injector = (injectors or {}).get(case_id)
        service.store.save_eval_case(summary.eval_id, run_case(service, model_, case, config=config, injector=injector))
    service.store.finish_eval_run(summary.eval_id, status, "2026-10-19T00:01:00+00:00")
    return summary.eval_id


def report(store, eval_id):
    return store.get_eval_report(eval_id)


# ---- counting what changed ----------------------------------------------------------------------------
def test_fixed_broken_and_unchanged_are_counted_per_case(service, store):
    a = build_eval(service, {"N1": True, "N2": False, "A1": True, "W1": False})
    b = build_eval(service, {"N1": False, "N2": True, "A1": True, "W1": False}, config=preset("guided"))
    result = compare(store, report(store, a), report(store, b))
    assert (result.matched, result.fixed, result.broken, result.still_passing, result.still_failing) == (4, 1, 1, 1, 1)
    assert {c.case_id: c.change for c in result.cases} == {
        "N1": "broken", "N2": "fixed", "A1": "still_passing", "W1": "still_failing"}
    assert (result.baseline.variant, result.candidate.variant) == ("baseline", "guided")
    n1 = result.cases[0]
    assert n1.baseline_passed and not n1.candidate_passed and "task_completion" in n1.candidate_failed_checks
    assert store.get_run(n1.baseline_run_id) and store.get_run(n1.candidate_run_id)  # every cell links to a real run


def test_checks_and_categories_are_compared_over_the_same_cases(service, store):
    a = build_eval(service, {"N1": True, "N2": False, "A1": True, "W1": False})
    b = build_eval(service, {"N1": True, "N2": True, "A1": True, "W1": True})
    result = compare(store, report(store, a), report(store, b))
    task = next(m for m in result.metrics if m.metric == "task_completion")
    assert (task.baseline_passed, task.baseline_total, task.candidate_passed, task.candidate_total) == (2, 4, 4, 4)
    assert result.metrics[0].gating and "latency" not in {m.metric for m in result.metrics}
    cats = {c.category: (c.total, c.baseline_passed, c.candidate_passed) for c in result.categories}
    assert cats == {"normal": (2, 1, 2), "ambiguous": (1, 1, 1), "wrong_tool": (1, 0, 1)}
    assert (result.fixed, result.broken) == (2, 0)


def test_a_case_only_one_side_ran_is_listed_but_not_counted_or_costed(service, store):
    a = build_eval(service, {"N1": True, "N2": True, "A1": True})
    b = build_eval(service, {"N1": True, "W1": True})
    result = compare(store, report(store, a), report(store, b))
    assert {c.case_id: c.change for c in result.cases} == {
        "N1": "still_passing", "N2": "only_baseline", "A1": "only_baseline", "W1": "only_candidate"}
    assert result.matched == 1 and result.baseline_cost.cases == 1 == result.candidate_cost.cases
    assert result.baseline_cost.tool_calls == 3 == result.candidate_cost.tool_calls  # N1 only


def test_cost_counts_retries_and_stays_honest_about_tokens(service, store):
    a = build_eval(service, {"N1": True})
    b = build_eval(service, {"N1": True}, config=preset("resilient"), injectors={"N1": FaultInjector([TIMEOUT])})
    result = compare(store, report(store, a), report(store, b))
    assert (result.baseline_cost.retries, result.candidate_cost.retries) == (0, 1)
    assert result.baseline_cost.tool_calls == result.candidate_cost.tool_calls == 3  # a retry is not an extra call
    assert result.candidate_cost.median_duration_ms >= 10  # the wait is real time
    assert result.baseline_cost.input_tokens is None  # the scripted model measures no tokens: none are invented
    assert result.candidate.variant == "resilient" and result.cases[0].candidate_retries == 1


def test_comparing_two_runs_of_the_same_agent_is_allowed_and_shows_the_noise(service, store):
    a = build_eval(service, {"N1": True, "N2": True})
    b = build_eval(service, {"N1": True, "N2": False})
    result = compare(store, report(store, a), report(store, b))
    assert (result.baseline.variant, result.candidate.variant) == ("baseline", "baseline")
    assert (result.fixed, result.broken) == (0, 1)


# ---- refusing an unfair comparison --------------------------------------------------------------------
def refusal(service, store, a, b):
    with pytest.raises(ComparisonError) as exc:
        compare(store, report(store, a), report(store, b))
    return str(exc.value)


def test_refuses_what_would_not_be_a_fair_comparison(service, store):
    base = build_eval(service, {"N1": True})
    assert "itself" in refusal(service, store, base, base)
    other_cases = build_eval(service, {"H1": True}, dataset=HOLDOUT)
    assert "different cases" in refusal(service, store, base, other_cases)
    assert "different models" in refusal(service, store, base, build_eval(service, {"N1": True}, model="ollama:x"))
    assert "different seeds" in refusal(service, store, build_eval(service, {"N1": True}, seed=0), build_eval(service, {"N1": True}, seed=1))
    assert "different kinds" in refusal(service, store, base, build_eval(service, {"N1": True}, kind="faultlab"))
    assert "has not finished" in refusal(service, store, base, build_eval(service, {"N1": True}, status="running"))
    validation = build_eval(service, {"N1": True}, kind="validation")
    assert "nothing to compare" in refusal(service, store, validation, build_eval(service, {"N1": True}, kind="validation"))


# ---- the failure lab, before and after ----------------------------------------------------------------
def test_lab_comparison_shows_which_faults_the_agent_now_survives(service, store):
    before = run_evaluation(service, GOLDEN, "faultlab")
    after = run_evaluation(service, GOLDEN, "faultlab", config=preset("full"))
    result = compare(store, report(store, before), report(store, after))
    effects = {c.case_id: (c.baseline_effect, c.candidate_effect) for c in result.cases}
    assert effects == {  # the predictions written in the plan before this was run
        "tool_timeout": ("run_failed", "no_effect"),
        "malformed_output": ("silent", "no_effect"),
        "wrong_tool": ("gating_failed", "gating_failed"),
        "model_error": ("run_failed", "no_effect"),
    }
    assert (result.fixed, result.broken, result.still_failing) == (3, 0, 1)
    assert result.candidate.variant == "full"
    assert result.candidate_cost.retries == 3 and result.baseline_cost.retries == 0


def test_a_recovered_fault_is_still_located_because_the_span_that_retried_is_a_suspect(service, store):
    run_evaluation(service, GOLDEN, "faultlab", config=preset("full"))
    (eval_id,) = [e.eval_id for e in store.list_eval_runs()]
    cases = {c.case_id: c.note for c in store.get_eval_report(eval_id).cases}
    for fault in ("tool_timeout", "malformed_output", "model_error"):
        assert cases[fault]["hit_at_1"], fault
        assert cases[fault]["suspects"][0]["source"] == "retried"
    assert cases["wrong_tool"]["hit_at_1"]


# ---- localizer: the retried tier ----------------------------------------------------------------------
def test_a_retried_span_is_the_weakest_suspect_and_found_by_event_name_not_text():
    from tests.test_localize import ROOT, span, traj

    retried = span("a", "tool.a", offset=1, events=[{"name": "retry", "attributes": {"exception.message": "nothing alarming"}}])
    (suspect,) = locate(traj(ROOT, retried), [])
    assert (suspect.span_id, suspect.tier, suspect.source) == ("a", 4, "retried") and "1 retry" in suspect.reason
    failed = span("b", "tool.b", offset=2, status="error", message="boom")
    assert [s.span_id for s in locate(traj(ROOT, retried, failed), [])] == ["b", "a"]
    text_only = span("c", "tool.c", offset=1, events=[{"name": "exception", "attributes": {"exception.message": "will retry later"}}])
    assert locate(traj(ROOT, text_only), []) == []  # the word in an event's text is not a retry


# ---- variants are recorded ----------------------------------------------------------------------------
def test_runs_and_evaluations_record_the_variant(service, store):
    eval_id = run_evaluation(service, GOLDEN, "reference", case_ids=["N1"], config=preset("guided"))
    rep = store.get_eval_report(eval_id)
    assert rep.variant == "guided" and store.get_run(rep.cases[0].run_id).variant == "guided"
    assert store.get_run(store.get_eval_report(run_evaluation(service, GOLDEN, "reference", case_ids=["N1"])).cases[0].run_id).variant == "baseline"
    assert [e.variant for e in store.list_eval_runs()] == ["baseline", "guided"]


def test_the_checks_validation_batch_refuses_a_variant(service):
    with pytest.raises(ValueError, match="baseline"):
        run_evaluation(service, GOLDEN, "faults", config=preset("full"))


def test_a_database_made_before_variants_existed_keeps_working(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE runs (run_id TEXT PRIMARY KEY, task TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
                           trace_id TEXT, started_at TEXT NOT NULL, duration_ms REAL, final_answer TEXT, error TEXT);
        CREATE TABLE eval_runs (eval_id TEXT PRIMARY KEY, kind TEXT NOT NULL, model TEXT NOT NULL,
                                dataset_version TEXT NOT NULL, dataset_hash TEXT NOT NULL, seed INTEGER,
                                started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL);
        INSERT INTO runs VALUES ('run-old', 'task', 'scripted:x', 'ok', NULL, '2026-10-01T00:00:00+00:00', 1.0, NULL, NULL);
        INSERT INTO eval_runs VALUES ('eval-old', 'benchmark', 'ollama:x', 'golden-v2', 'abc', 0, '2026-10-01T00:00:00+00:00', NULL, 'done');
    """)
    old.commit()
    old.close()
    store = Store(path)
    assert store.get_run("run-old").variant == "baseline"
    assert store.list_eval_runs()[0].variant == "baseline"
    store.close()
    Store(path).close()  # opening twice must not try to add the column again


# ---- API ----------------------------------------------------------------------------------------------
@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def post_eval(client, **body):
    r = client.post("/evals", json=body)
    assert r.status_code in (202, 422), r.text
    return r


def test_api_compares_two_stored_evaluations(client):
    a = post_eval(client, mode="faultlab").json()["eval_id"]
    b = post_eval(client, mode="faultlab", variant="full").json()["eval_id"]
    r = client.get("/evals/compare", params={"baseline": a, "candidate": b})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["fixed"], body["broken"], body["kind"]) == (3, 0, "faultlab")
    assert body["candidate"]["variant"] == "full" and body["cases"][0]["baseline_run_id"]
    assert client.get(f"/evals/{b}").json()["variant"] == "full"  # the route order keeps /evals/{id} working


def test_api_explains_why_two_evaluations_cannot_be_compared(client):
    a = post_eval(client, mode="faultlab").json()["eval_id"]
    b = post_eval(client, mode="reference").json()["eval_id"]
    r = client.get("/evals/compare", params={"baseline": a, "candidate": b})
    assert r.status_code == 422 and "different kinds" in r.json()["detail"]
    assert client.get("/evals/compare", params={"baseline": a, "candidate": "nope"}).status_code == 404
    assert client.get("/evals/compare", params={"baseline": a, "candidate": a}).status_code == 422


def test_api_variants_are_validated(client):
    assert post_eval(client, mode="reference", variant="turbo").status_code == 422
    assert post_eval(client, mode="faults", variant="full").status_code == 422
    r = client.post("/runs", json={"task": "Refund order 42.", "variant": "turbo"})
    assert r.status_code == 422


def test_api_runs_record_the_variant(client):
    run = client.post("/runs", json={"task": "Order 42 arrived damaged, please refund it.", "variant": "resilient"}).json()
    assert run["variant"] == "resilient"
    assert client.get(f"/runs/{run['run_id']}").json()["variant"] == "resilient"
    assert client.post("/runs", json={"task": "x"}).json()["variant"] == "baseline"


# ---- CLI ----------------------------------------------------------------------------------------------
def test_cli_runs_a_variant_and_compares(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BLACKBOX_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("BLACKBOX_OTLP_ENDPOINT", "")
    cli_main(["run", "--mode", "faultlab"])
    cli_main(["run", "--mode", "faultlab", "--variant", "full"])
    out = capsys.readouterr().out
    assert "faultlab [baseline]" in out and "faultlab [full]" in out
    store = Store(str(tmp_path / "cli.db"))
    first, second = (e.eval_id for e in reversed(store.list_eval_runs()))
    store.close()
    cli_main(["compare", first, second])
    text = capsys.readouterr().out
    assert "3 fixed, 0 broken" in text and "run_failed -> no_effect" in text and "retries 0 -> 3" in text
    with pytest.raises(SystemExit, match="Cannot compare"):
        cli_main(["compare", first, first])
    with pytest.raises(SystemExit, match="baseline"):
        cli_main(["run", "--mode", "faults", "--variant", "full"])
