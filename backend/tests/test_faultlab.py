"""The failure lab end to end on the scripted model: plant each fault, evaluate from the stored trace,
ask the localizer where to look, and score it against the span the injector recorded."""
import pytest
from fastapi.testclient import TestClient

from blackbox.api.main import create_app
from blackbox.evals.cases import load_dataset
from blackbox.evals.faultlab import LAB_FAULTS, _warm_up, effect_of
from blackbox.llm.base import ModelResponse
from blackbox.evals.runner import run_evaluation

DATASET = load_dataset()


@pytest.fixture
def lab(service, store):
    eval_id = run_evaluation(service, DATASET, "faultlab")
    report = store.get_eval_report(eval_id)
    return report, {c.case_id: c for c in report.cases}


def test_the_lab_is_stored_as_a_faultlab_evaluation(lab):
    report, _ = lab
    assert report.kind == "faultlab" and report.model == "scripted:faultlab" and report.status == "done"
    assert [c.case_id for c in report.cases] == [f.name for f in LAB_FAULTS]
    assert (report.n_cases, report.n_passed) == (4, 4)  # "passed" = the top suspect is the injected span


EXPECTED = {
    # fault: (what it did to the run, name of the span trace analysis should put first)
    "tool_timeout": ("run_failed", "tool.check_refund_policy"),
    "malformed_output": ("silent", "tool.lookup_order"),
    "wrong_tool": ("gating_failed", "tool.update_shipping_address"),
    "model_error": ("run_failed", "model.call"),
}


@pytest.mark.parametrize("name", EXPECTED)
def test_each_fault_has_the_expected_effect_and_is_located_at_rank_one(lab, name):
    _, cases = lab
    note = cases[name].note
    effect, span_name = EXPECTED[name]
    assert note["effect"] == effect
    assert note["fired"] is True
    assert note["origin_span_name"] == span_name
    assert note["rank"] == 1 and note["hit_at_1"] and note["hit_at_3"]
    assert note["suspects"][0]["span_id"] == note["origin_span_id"]
    assert note["suspects"][0]["span_name"] == span_name


def test_the_silent_fault_passes_both_gating_checks_and_only_the_contract_check_notices(lab):
    _, cases = lab
    case = cases["malformed_output"]
    assert case.note["faulted"]["gating_passed"] is True and case.note["faulted"]["run_status"] == "ok"
    assert case.note["faulted"]["failed_checks"] == ["tool_output_contract"]
    assert case.note["suspects"][0]["tier"] == 0 and case.note["suspects"][0]["source"] == "tool output contract"


def test_the_loud_faults_fail_the_run_and_the_error_is_the_signal(lab):
    _, cases = lab
    for name in ("tool_timeout", "model_error"):
        faulted = cases[name].note["faulted"]
        assert faulted["run_status"] == "error" and faulted["gating_passed"] is False
        assert cases[name].note["suspects"][0]["tier"] == 3  # error status: the run span is not listed as a cause
        assert len(cases[name].note["suspects"]) == 1


def test_wrong_tool_is_found_through_the_policy_check_not_through_an_error(lab):
    _, cases = lab
    note = cases["wrong_tool"].note
    assert note["suspects"][0]["tier"] == 1 and note["suspects"][0]["source"] == "policy compliance"
    assert "without a successful lookup" in note["suspects"][0]["reason"]


def test_every_lab_run_is_compared_with_the_same_untouched_control(lab):
    _, cases = lab
    controls = {c.note["control"]["run_id"] for c in cases.values()}
    assert len(controls) == 1  # one control run, shared
    control = next(iter(cases.values())).note["control"]
    assert control["run_status"] == "ok" and control["gating_passed"] is True and control["failed_checks"] == []
    assert control["tool_calls"] == 3
    assert cases["tool_timeout"].note["faulted"]["duration_ms"] > control["duration_ms"]  # the timeout is real elapsed time


def test_effect_labels():
    base = {"run_status": "ok", "gating_passed": True, "failed_checks": []}
    assert effect_of(base) == "no_effect"
    assert effect_of({**base, "failed_checks": ["step_efficiency"]}) == "silent"
    assert effect_of({**base, "gating_passed": False}) == "gating_failed"
    assert effect_of({**base, "run_status": "error", "gating_passed": False}) == "run_failed"


def test_ground_truth_is_stored_outside_the_trace_and_never_in_it(lab, store):
    _, cases = lab
    run_id = cases["tool_timeout"].run_id
    (fault,) = store.get_run_faults(run_id)
    assert fault.kind == "tool_timeout" and fault.fired and fault.origin_span_id == cases["tool_timeout"].note["origin_span_id"]
    assert {s.span_id for s in store.get_spans(run_id)} >= {fault.origin_span_id}
    control_run = cases["tool_timeout"].note["control"]["run_id"]
    assert store.get_run_faults(control_run) == []  # the control run had nothing planted


def test_the_lab_through_the_api(settings):
    with TestClient(create_app(settings)) as client:
        eval_id = client.post("/evals", json={"mode": "faultlab"}).json()["eval_id"]
        report = client.get(f"/evals/{eval_id}").json()
        assert report["kind"] == "faultlab" and report["n_passed"] == 4

        case = next(c for c in report["cases"] if c["case_id"] == "wrong_tool")
        faults = client.get(f"/runs/{case['run_id']}/faults").json()
        assert faults[0]["kind"] == "wrong_tool" and faults[0]["origin_span_id"] == case["note"]["origin_span_id"]

        evaluation = client.get(f"/runs/{case['run_id']}/evaluation").json()
        assert evaluation["suspects"][0]["span_id"] == case["note"]["origin_span_id"]  # "where to look first", for any run

        plain = client.post("/runs", json={"task": "Refund order 42"}).json()["run_id"]
        assert client.get(f"/runs/{plain}/faults").json() == []
        assert client.get(f"/runs/{plain}/evaluation").json()["suspects"] == []  # a healthy run has nothing to suspect
        assert client.get("/runs/nope/faults").status_code == 404


class _FakeLocalModel:
    provider = "ollama"
    name = "fake"

    def __init__(self, fail: bool = False):
        self.calls, self.fail = [], fail

    def chat(self, messages, tools):
        self.calls.append((messages, tools))
        if self.fail:
            raise ConnectionError("not running")
        return ModelResponse(content="ready")


def test_a_real_model_is_loaded_before_timing_but_a_scripted_one_is_left_alone():
    local = _FakeLocalModel()
    _warm_up(local)
    assert len(local.calls) == 1 and local.calls[0][1] == []  # one tiny request, no tools

    from blackbox.evals.scripts import reference_model
    scripted = reference_model(DATASET.case("N1"))
    _warm_up(scripted)
    assert scripted.chat([], []).tool_calls[0].name == "lookup_order"  # its script was not consumed


def test_a_failed_warm_up_does_not_stop_the_lab():
    _warm_up(_FakeLocalModel(fail=True))  # no exception: the real runs will record the failure themselves
