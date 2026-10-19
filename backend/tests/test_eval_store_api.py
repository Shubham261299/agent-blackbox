import pytest
from fastapi.testclient import TestClient

from blackbox.api.main import create_app
from blackbox.evals.__main__ import main as cli_main
from blackbox.evals.cases import load_dataset
from blackbox.evals.runner import run_evaluation
from blackbox.models import RunRecord

DATASET = load_dataset()


# ---------------------------------------------------------------- runner and store
def test_reference_evaluation_is_stored_and_summarised(service, store):
    eval_id = run_evaluation(service, DATASET, "reference")
    report = store.get_eval_report(eval_id)
    assert report.kind == "reference" and report.status == "done"
    assert report.dataset_version == "golden-v3" and report.dataset_hash == DATASET.content_hash
    assert (report.n_cases, report.n_passed) == (24, 24)

    metrics = {m.metric: m for m in report.metrics}
    assert list(metrics)[:2] == ["task_completion", "policy_compliance"]  # fixed display order
    assert metrics["task_completion"].gating and not metrics["tool_correctness"].gating
    assert (metrics["task_completion"].passed, metrics["task_completion"].total) == (24, 24)
    assert metrics["latency"].total == 0  # informational: never counted as pass/fail
    assert {c.category: (c.passed, c.total) for c in report.categories} == {
        "normal": (8, 8), "ambiguous": (4, 4), "wrong_tool": (4, 4), "tool_failure": (4, 4), "constraint": (4, 4)}


def test_case_filter_and_run_links(service, store):
    eval_id = run_evaluation(service, DATASET, "reference", case_ids=["N1", "W3"])
    report = store.get_eval_report(eval_id)
    assert [c.case_id for c in report.cases] == ["N1", "W3"]
    first = report.cases[0]
    assert store.get_run(first.run_id) is not None and store.find_eval_case_for_run(first.run_id) == (eval_id, "N1")
    assert {c.metric for c in first.checks} >= {"task_completion", "latency"}


def test_validation_batch_records_what_each_fault_should_trip(service, store):
    eval_id = run_evaluation(service, DATASET, "faults")
    report = store.get_eval_report(eval_id)
    assert report.kind == "validation" and (report.n_cases, report.n_passed) == (11, 11)
    skip = next(c for c in report.cases if c.case_id == "skips_policy_check")
    assert skip.note["expected_fail"] == ["policy_compliance", "tool_correctness"] and skip.note["matched"]


def test_eval_runs_are_listed_newest_first(service, store):
    first = run_evaluation(service, DATASET, "reference", case_ids=["N7"])
    second = run_evaluation(service, DATASET, "reference", case_ids=["N7"])
    assert [e.eval_id for e in store.list_eval_runs()] == [second, first]
    assert store.get_eval_report("nope") is None


# ---------------------------------------------------------------- API
@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def test_start_reference_eval_over_the_api(client):
    started = client.post("/evals", json={"mode": "reference"})
    assert started.status_code == 202 and started.json()["status"] == "running"

    listed = client.get("/evals").json()
    assert listed[0]["eval_id"] == started.json()["eval_id"] and listed[0]["status"] == "done"
    report = client.get(f"/evals/{listed[0]['eval_id']}").json()
    assert report["n_passed"] == 24 and len(report["cases"]) == 24
    assert {m["metric"] for m in report["metrics"]} >= {"task_completion", "step_efficiency"}


def test_faults_mode_over_the_api_and_validation_of_the_request(client):
    eval_id = client.post("/evals", json={"mode": "faults"}).json()["eval_id"]
    report = client.get(f"/evals/{eval_id}").json()
    assert report["kind"] == "validation" and report["n_passed"] == 11
    assert client.post("/evals", json={"mode": "ollama"}).status_code == 422  # real runs belong to the CLI
    assert client.get("/evals/nope").status_code == 404


def test_run_evaluation_returns_stored_checks_for_a_case_run(client):
    eval_id = client.post("/evals", json={"mode": "reference"}).json()["eval_id"]
    report = client.get(f"/evals/{eval_id}").json()
    case = next(c for c in report["cases"] if c["case_id"] == "N1")
    body = client.get(f"/runs/{case['run_id']}/evaluation").json()
    assert body["stored"] is True and body["case_id"] == "N1" and body["eval_id"] == eval_id
    assert len(body["checks"]) == 8


def test_any_run_gets_the_expectation_free_checks_on_the_fly(client):
    run_id = client.post("/runs", json={"task": "Refund order 42"}).json()["run_id"]
    body = client.get(f"/runs/{run_id}/evaluation").json()
    assert body["stored"] is False and body["case_id"] is None
    assert [c["metric"] for c in body["checks"]] == ["policy_compliance", "trace_completeness", "tool_output_contract", "latency"]
    assert all(c["passed"] in (True, None) for c in body["checks"])


def test_evaluation_endpoint_edge_cases(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/runs/nope/evaluation").status_code == 404
        app.state.store.create_run(RunRecord(run_id="run-busy", task="t", model="m", status="running", started_at="now"))
        assert client.get("/runs/run-busy/evaluation").status_code == 409


def test_a_policy_violation_in_a_real_run_points_at_its_span(client):
    # the 'skips_policy_check' fault, evaluated through the same endpoint a person would use
    eval_id = client.post("/evals", json={"mode": "faults"}).json()["eval_id"]
    report = client.get(f"/evals/{eval_id}").json()
    case = next(c for c in report["cases"] if c["case_id"] == "skips_policy_check")
    body = client.get(f"/runs/{case['run_id']}/evaluation").json()
    policy = next(c for c in body["checks"] if c["metric"] == "policy_compliance")
    assert policy["passed"] is False and len(policy["span_ids"]) == 1
    spans = {s["span_id"]: s for s in client.get(f"/runs/{case['run_id']}/spans").json()}
    assert spans[policy["span_ids"][0]]["name"] == "tool.issue_refund"


# ---------------------------------------------------------------- CLI
def test_cli_runs_a_batch_and_prints_a_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BLACKBOX_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("BLACKBOX_OTLP_ENDPOINT", "")
    cli_main(["run", "--mode", "reference", "--cases", "N1,A1"])
    out = capsys.readouterr().out
    assert "2/2 passed" in out and "PASS  N1" in out and "task_completion" in out


def test_cli_rejects_unknown_cases(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACKBOX_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("BLACKBOX_OTLP_ENDPOINT", "")
    with pytest.raises(SystemExit) as exc:
        cli_main(["run", "--mode", "reference", "--cases", "N1,ZZ9"])
    assert "ZZ9" in str(exc.value)


def test_cli_stops_before_running_when_ollama_is_unreachable(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACKBOX_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("BLACKBOX_OTLP_ENDPOINT", "")
    monkeypatch.setenv("BLACKBOX_OLLAMA_HOST", "http://127.0.0.1:9")
    with pytest.raises(SystemExit) as exc:
        cli_main(["run", "--mode", "ollama"])
    assert "Cannot reach Ollama" in str(exc.value) and "No hosted model" in str(exc.value)
