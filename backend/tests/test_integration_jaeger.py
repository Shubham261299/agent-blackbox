"""Needs a local Jaeger:  docker compose up -d jaeger   (skipped automatically when it is not reachable)."""
import json
import socket
import time
import urllib.error
import urllib.request

import pytest

from blackbox.agent.loop import AgentRunner
from blackbox.agent.tools import OrderDesk
from blackbox.config import Settings
from blackbox.llm.scripted import scripted_model
from blackbox.store.db import Store
from blackbox.telemetry.setup import Telemetry

pytestmark = pytest.mark.integration

JAEGER_QUERY = "http://localhost:16686"


def _reachable(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture
def jaeger():
    if not (_reachable(16686) and _reachable(4318)):
        pytest.skip("Jaeger not running on :16686/:4318")


def _fetch_trace(trace_id: str, expected_spans: int, timeout_s: float = 15.0):
    deadline = time.time() + timeout_s
    spans = []
    while time.time() < deadline:
        try:
            data = json.load(urllib.request.urlopen(f"{JAEGER_QUERY}/api/v3/traces/{trace_id}", timeout=5))
            spans = [s for rs in data["result"]["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]]
        except urllib.error.HTTPError:
            spans = []  # not indexed yet
        if len(spans) >= expected_spans:
            return spans
        time.sleep(0.5)
    return spans


def test_run_reaches_jaeger_and_matches_sqlite_copy(jaeger):
    settings = Settings(db_path=":memory:")  # default OTLP endpoint -> local Jaeger
    store = Store(":memory:")
    telemetry = Telemetry(settings, store)
    try:
        run_id = f"it-{int(time.time())}"
        result = AgentRunner(scripted_model("unknown_order"), OrderDesk().registry(), telemetry.tracer()).run(
            run_id, "Where is order 999?"
        )
        telemetry.flush()

        mine = store.get_spans(run_id)
        theirs = _fetch_trace(result.trace_id, expected_spans=len(mine))
    finally:
        telemetry.shutdown()
        store.close()

    assert len(mine) == 4  # agent.run, model.plan, tool.lookup_order, model.finalize
    assert sorted(s.name for s in mine) == sorted(s["name"] for s in theirs)
    by_id = {s["spanId"]: s for s in theirs}
    for record in mine:
        remote = by_id[record.span_id]
        assert (remote.get("parentSpanId") or None) == record.parent_span_id
        assert (remote.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR")) == (record.status == "error")
    # redaction applies to Jaeger too, not just SQLite
    assert "example.com" not in json.dumps(theirs)
