import time

import pytest
from fastapi.testclient import TestClient

from blackbox.api.main import create_app
from blackbox.config import Settings


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_scenarios_listed_and_every_one_is_runnable(client):
    from blackbox.llm.scripted import SCENARIOS

    scenarios = client.get("/scenarios").json()
    assert {s["name"] for s in scenarios} == set(SCENARIOS)  # info and scripts cannot drift apart
    for s in scenarios:
        assert s["description"] and s["example_task"]
        run_id = client.post("/runs", json={"task": s["example_task"], "scenario": s["name"]}).json()["run_id"]
        assert client.get(f"/runs/{run_id}").json()["status"] == "ok"


def test_start_run_then_read_run_and_spans(client):
    started = client.post("/runs", json={"task": "Refund order 42, damaged."})
    assert started.status_code == 202
    body = started.json()
    assert body["status"] == "running" and body["model"] == "scripted:refund_happy_path"

    run = client.get(f"/runs/{body['run_id']}").json()
    assert run["status"] == "ok" and "$59.90" in run["final_answer"]
    assert run["trace_id"] and run["duration_ms"] > 0

    spans = client.get(f"/runs/{body['run_id']}/spans").json()
    assert [s["name"] for s in spans][0] == "agent.run" and len(spans) == 8
    assert {s["trace_id"] for s in spans} == {run["trace_id"]}


def test_list_runs_newest_first(client):
    first = client.post("/runs", json={"task": "a", "scenario": "unknown_order"}).json()["run_id"]
    second = client.post("/runs", json={"task": "b", "scenario": "refund_denied_over_limit"}).json()["run_id"]
    assert [r["run_id"] for r in client.get("/runs").json()] == [second, first]


def test_run_row_does_not_store_raw_pii(client):
    run_id = client.post("/runs", json={"task": "Refund order 42 for ava.martin@example.com"}).json()["run_id"]
    task = client.get(f"/runs/{run_id}").json()["task"]
    assert "example.com" not in task and "[REDACTED_EMAIL]" in task


def test_not_found_and_validation_errors(client):
    assert client.get("/runs/nope").status_code == 404
    assert client.get("/runs/nope/spans").status_code == 404
    assert client.post("/runs", json={"task": "x", "scenario": "does_not_exist"}).status_code == 422
    assert client.post("/runs", json={"task": ""}).status_code == 422
    assert client.post("/runs", json={"task": "x", "model": "gpt-4"}).status_code == 422


def test_unreachable_jaeger_neither_breaks_nor_delays_a_run():
    dead_jaeger = Settings(db_path=":memory:", otlp_endpoint="http://127.0.0.1:9/v1/traces")
    with TestClient(create_app(dead_jaeger)) as client:
        t0 = time.perf_counter()
        run_id = client.post("/runs", json={"task": "Refund order 42"}).json()["run_id"]
        elapsed = time.perf_counter() - t0
        run = client.get(f"/runs/{run_id}").json()
        assert run["status"] == "ok" and run["duration_ms"] < 1000
        assert elapsed < 3  # the OTLP exporter alone would block ~5 s if the run waited for it
        assert len(client.get(f"/runs/{run_id}/spans").json()) == 8  # SQLite copy is complete regardless


def test_unreachable_ollama_fails_the_run_and_never_falls_back():
    unreachable = Settings(db_path=":memory:", otlp_endpoint=None, ollama_host="http://127.0.0.1:9", ollama_timeout_s=2)
    with TestClient(create_app(unreachable)) as client:
        run_id = client.post("/runs", json={"task": "Refund order 42", "model": "ollama"}).json()["run_id"]
        run = client.get(f"/runs/{run_id}").json()
        assert run["status"] == "error" and run["error"]
        assert run["model"].startswith("ollama:")
        spans = client.get(f"/runs/{run_id}/spans").json()
        assert {s["name"]: s["status"] for s in spans} == {"agent.run": "error", "model.call": "error"}
