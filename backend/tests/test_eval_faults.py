"""The fault catalog validates the checks themselves: each planted fault runs through the real agent loop,
tracer and store, and must trip exactly the checks it is meant to, no more and no fewer."""
import pytest

from blackbox.evals.cases import load_dataset
from blackbox.evals.runner import _fault_result
from blackbox.evals.scripts import FAULTS

DATASET = load_dataset()
JUDGED = {"task_completion", "policy_compliance", "tool_correctness", "argument_correctness",
          "step_efficiency", "trace_completeness"}


@pytest.mark.parametrize("fault", FAULTS, ids=[f.name for f in FAULTS])
def test_fault_trips_exactly_the_expected_checks(fault, service):
    result = _fault_result(service, DATASET, fault)
    failed = {c.metric for c in result.checks if c.passed is False}
    assert failed == set(fault.expect_fail), {c.metric: c.reason for c in result.checks if c.passed is False}
    assert result.note["matched"] is True and result.passed is True  # "passed" = the checks reacted as expected


def test_every_judged_metric_is_proven_by_at_least_one_fault():
    covered = set().union(*(f.expect_fail for f in FAULTS))
    assert covered == JUDGED


def test_the_control_fault_proves_nothing_fails_on_a_correct_run():
    control = next(f for f in FAULTS if f.name == "control")
    assert control.expect_fail == frozenset()


def test_fault_names_are_unique_and_point_at_real_cases():
    assert len({f.name for f in FAULTS}) == len(FAULTS)
    assert {f.base_case for f in FAULTS} <= {c.id for c in DATASET.cases}
