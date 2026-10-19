"""The resilient agent: retries with a limit, runtime contract enforcement, and proof that the baseline agent and
the trace shape are untouched. The injector plants the failures; a retry is judged by what is in the stored trace."""
import json

import pytest

from blackbox.agent.config import PRESETS, AgentConfig, preset
from blackbox.evals.cases import load_dataset
from blackbox.evals.checks import case_passed, evaluate_case
from blackbox.evals.scripts import reference_script
from blackbox.evals.trajectory import build_trajectory
from blackbox.faults.injector import FaultInjector, FaultSpec
from blackbox.llm.scripted import ScriptedModel, scripted_model

N1 = load_dataset().case("N1")
RESILIENT = preset("resilient")
HAPPY_NAMES = ["agent.run", "model.plan", "tool.lookup_order", "model.call", "tool.check_refund_policy",
               "model.call", "tool.issue_refund", "model.finalize"]
TIMEOUT = FaultSpec("tool_timeout", tool="check_refund_policy", params={"delay_s": 0.01})
MALFORMED = FaultSpec("malformed_output", tool="lookup_order", params={"mode": "html"})
MODEL_ERROR = FaultSpec("model_error", occurrence=2)


def persistent(spec: FaultSpec) -> FaultSpec:
    return FaultSpec(spec.kind, spec.tool, spec.occurrence, {**spec.params, "persistent": True})


@pytest.fixture
def go(service, store):
    """Run N1 on the scripted reference model with the given faults and config. Returns (run, trajectory, injector)."""
    def _go(*specs, config=RESILIENT, script=None):
        injector = FaultInjector(list(specs))
        model = ScriptedModel(script or reference_script(N1), name="ref")
        run = service.run_sync(model, N1.task, injector=injector, config=config)
        return run, build_trajectory(run, store.get_spans(run.run_id)), injector
    return _go


def retry_events(traj, span_name):
    span = next(s for s in traj.spans if s.name == span_name)
    return [e for e in span.events if e["name"] == "retry"]


# ---- the baseline is untouched ------------------------------------------------------------------------
def test_baseline_config_is_the_default_and_adds_nothing(run_agent, store):
    assert PRESETS["baseline"] == AgentConfig() and AgentConfig().retries == 0 and not AgentConfig().enforce_contracts
    run_agent(scripted_model("refund_happy_path"))
    spans = store.get_spans("run-test")
    assert [s.name for s in spans] == HAPPY_NAMES
    assert "blackbox.agent.variant" not in spans[0].attributes
    assert all(not s.events and "blackbox.agent.retry_count" not in s.attributes for s in spans)


def test_baseline_still_dies_on_a_timeout_and_a_model_error(go):
    for spec in (TIMEOUT, MODEL_ERROR):
        run, traj, _ = go(spec, config=preset("baseline"))
        assert run.status == "error"
        assert not [e for s in traj.spans for e in s.events if e["name"] == "retry"]


def test_baseline_lets_malformed_output_through(go):
    run, traj, _ = go(MALFORMED, config=preset("baseline"))
    assert run.status == "ok" and traj.calls("lookup_order")[0].output == "<html><body><h1>502 Bad Gateway</h1></body></html>"


def test_unknown_variant_is_rejected():
    with pytest.raises(KeyError, match="unknown agent variant"):
        preset("turbo")


# ---- retries recover a transient failure --------------------------------------------------------------
def test_a_tool_timeout_is_retried_and_the_run_completes(go):
    run, traj, injector = go(TIMEOUT)
    assert run.status == "ok" and injector.faults[0].fired
    assert [s.name for s in traj.spans] == HAPPY_NAMES  # one span per call the model made: retries do not add spans
    span = next(s for s in traj.spans if s.name == "tool.check_refund_policy")
    assert span.status == "ok" and span.attributes["blackbox.agent.retry_count"] == 1
    (event,) = retry_events(traj, "tool.check_refund_policy")
    assert event["attributes"]["retry.attempt"] == 1 and "timed out" in event["attributes"]["exception.message"]
    assert traj.root.attributes["blackbox.agent.variant"] == "resilient"
    assert case_passed(evaluate_case(N1, traj))


def test_a_model_error_is_retried_and_the_run_completes(go):
    run, traj, _ = go(MODEL_ERROR)
    assert run.status == "ok" and [s.name for s in traj.spans] == HAPPY_NAMES
    step2 = next(s for s in traj.spans if s.name == "model.call" and s.attributes["blackbox.agent.step"] == 2)
    assert step2.status == "unset" and step2.attributes["blackbox.agent.retry_count"] == 1
    assert [e["name"] for e in step2.events] == ["retry"]
    assert case_passed(evaluate_case(N1, traj))


@pytest.mark.parametrize("error", [ConnectionError("refused"), TimeoutError("slow")])
def test_other_connection_errors_count_as_a_model_outage(service, store, error):
    class Flaky(ScriptedModel):
        failed = False

        def chat(self, messages, tools):
            if not self.failed:
                self.failed = True
                raise error
            return super().chat(messages, tools)

    run = service.run_sync(Flaky(reference_script(N1)), N1.task, config=RESILIENT)
    assert run.status == "ok"


def test_a_bug_in_the_model_client_is_not_retried(service):
    class Broken(ScriptedModel):
        calls = 0

        def chat(self, messages, tools):
            self.calls += 1
            raise ValueError("bad payload")

    model = Broken([])
    run = service.run_sync(model, N1.task, config=RESILIENT)
    assert run.status == "error" and model.calls == 1


# ---- the limit is a limit -----------------------------------------------------------------------------
def test_a_persistent_tool_timeout_stops_after_the_retry_limit(go):
    run, traj, injector = go(persistent(TIMEOUT))
    assert injector._calls["check_refund_policy"] == 3  # the first attempt plus exactly two retries
    span = next(s for s in traj.spans if s.name == "tool.check_refund_policy")
    assert span.status == "error" and span.attributes["blackbox.agent.retry_count"] == 2
    assert [e["name"] for e in span.events] == ["retry", "retry", "exception"]
    assert json.loads(span.attributes["blackbox.tool.output"])["error"].startswith("check_refund_policy timed out")
    assert run.status == "ok"  # the agent was told, so the run goes on instead of dying
    assert injector.faults[0].origin_span_id == span.span_id  # still the first span the fault hit


def test_a_persistent_model_error_stops_after_the_retry_limit_and_ends_the_run(go):
    run, traj, _ = go(persistent(MODEL_ERROR))
    failing = next(s for s in traj.spans if s.name == "model.call" and s.status == "error")
    assert failing.attributes["blackbox.agent.retry_count"] == 2
    assert [e["name"] for e in failing.events] == ["retry", "retry", "exception"]
    assert run.status == "error" and "ModelUnavailableError" in run.error


def test_the_retry_limit_comes_from_the_config(go):
    _, _, injector = go(persistent(TIMEOUT), config=AgentConfig(name="x", retries=4))
    assert injector._calls["check_refund_policy"] == 5
    _, _, injector = go(persistent(TIMEOUT), config=AgentConfig(name="x", retries=1))
    assert injector._calls["check_refund_policy"] == 2


def test_a_domain_error_is_not_retried(go):
    script = [r for r in scripted_model("unknown_order")._responses]
    run, traj, injector = go(script=script)
    assert traj.calls("lookup_order")[0].status == "error"
    assert injector._calls["lookup_order"] == 1 and not retry_events(traj, "tool.lookup_order")
    assert run.status == "ok"


# ---- contract enforcement -----------------------------------------------------------------------------
def test_malformed_output_is_rejected_and_retried(go):
    run, traj, _ = go(MALFORMED)
    (event,) = retry_events(traj, "tool.lookup_order")
    assert "invalid output" in event["attributes"]["exception.message"] and "expected an object" in event["attributes"]["exception.message"]
    lookup = traj.calls("lookup_order")[0]
    assert lookup.status == "ok" and lookup.output["order_id"] == 42  # the model only ever saw the good answer
    assert run.status == "ok" and case_passed(evaluate_case(N1, traj))
    assert next(r for r in evaluate_case(N1, traj) if r.metric == "tool_output_contract").passed is True


def test_persistent_malformed_output_ends_as_a_failed_call_not_a_silent_one(go):
    run, traj, injector = go(persistent(MALFORMED))
    assert injector._calls["lookup_order"] == 3
    lookup = traj.calls("lookup_order")[0]
    assert lookup.status == "error" and "invalid output" in lookup.output["error"]
    checks = {c.metric: c for c in evaluate_case(N1, traj)}
    assert checks["tool_output_contract"].passed is True  # a failed call is not a silent one; the failure is visible
    assert checks["trace_completeness"].passed is True


def test_contracts_alone_reject_without_retrying(go):
    config = AgentConfig(name="contracts-only", enforce_contracts=True)
    _, traj, injector = go(MALFORMED, config=config)
    assert injector._calls["lookup_order"] == 1
    assert traj.calls("lookup_order")[0].status == "error" and not retry_events(traj, "tool.lookup_order")


def test_retries_alone_do_not_enforce_contracts(go):
    config = AgentConfig(name="retries-only", retries=2)
    run, traj, injector = go(MALFORMED, config=config)
    assert injector._calls["lookup_order"] == 1 and traj.calls("lookup_order")[0].status == "ok"


def test_valid_output_is_never_flagged_by_the_contracts(go):
    run, traj, _ = go()
    assert run.status == "ok" and not [e for s in traj.spans for e in s.events]
    assert [s.name for s in traj.spans] == HAPPY_NAMES


# ---- the injector's persistent option -----------------------------------------------------------------
def test_a_non_persistent_fault_still_fires_once(go):
    _, _, injector = go(TIMEOUT, config=preset("resilient"))
    assert injector._calls["check_refund_policy"] == 2  # failed once, then the retry went through


def test_persistent_means_from_the_given_occurrence_on():
    spec = FaultSpec("tool_timeout", tool="x", occurrence=2, params={"persistent": True})
    assert [spec.matches(n) for n in (1, 2, 3, 9)] == [False, True, True, True]
    once = FaultSpec("tool_timeout", tool="x", occurrence=2)
    assert [once.matches(n) for n in (1, 2, 3)] == [False, True, False]
