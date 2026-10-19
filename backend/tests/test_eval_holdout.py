"""The held-out dataset (written before any Day 5 fix) must be consistent, must not overlap the golden set,
and a scripted correct run of every case must pass every check."""
import re
from collections import Counter

import pytest

from blackbox.agent.tools import OrderDesk
from blackbox.evals.cases import load_dataset
from blackbox.evals.checks import case_passed
from blackbox.evals.runner import run_case
from blackbox.evals.scripts import reference_model

HOLDOUT = load_dataset("holdout-v1")
GOLDEN = load_dataset("golden-v2")
CASE_IDS = [c.id for c in HOLDOUT.cases]
KNOWN_TOOLS = set(OrderDesk().registry())


def test_holdout_shape():
    assert HOLDOUT.version == "holdout-v1" and len(HOLDOUT.content_hash) == 12
    assert len(HOLDOUT.cases) == 8 and len(set(CASE_IDS)) == 8
    assert Counter(c.category for c in HOLDOUT.cases) == {
        "normal": 2, "ambiguous": 3, "wrong_tool": 1, "constraint": 2}


def test_holdout_does_not_overlap_the_golden_set():
    golden_ids = {c.id for c in GOLDEN.cases}
    assert not set(CASE_IDS) & golden_ids
    golden_tasks = {c.task.lower() for c in GOLDEN.cases}
    assert not {c.task.lower() for c in HOLDOUT.cases} & golden_tasks
    assert HOLDOUT.content_hash != GOLDEN.content_hash


@pytest.mark.parametrize("case", HOLDOUT.cases, ids=CASE_IDS)
def test_case_references_real_tools_and_orders(case):
    desk = OrderDesk()
    calls = [*case.required_calls, *case.optional_calls]
    assert {c.tool for c in calls} | set(case.forbidden_tools) <= KNOWN_TOOLS
    assert not {c.tool for c in calls} & set(case.forbidden_tools)
    ids = [c.args.get("order_id") for c in calls]
    ids += [r.order_id for r in case.outcome.refunds] + [a.order_id for a in case.outcome.address_changes]
    assert all(i in desk.orders for i in ids if i is not None)
    assert case.optimal_tool_calls >= len(case.required_calls)
    for pattern in [*case.answer_must_match_any, *case.answer_must_not_match]:
        re.compile(pattern)


@pytest.mark.parametrize("case", HOLDOUT.cases, ids=CASE_IDS)
def test_reference_answer_satisfies_its_own_patterns(case):
    if case.answer_must_match_any:
        assert any(re.search(p, case.reference_answer, re.I) for p in case.answer_must_match_any)
    assert not any(re.search(p, case.reference_answer, re.I) for p in case.answer_must_not_match)


@pytest.mark.parametrize("case", HOLDOUT.cases, ids=CASE_IDS)
def test_scripted_correct_run_passes_every_check(case, service):
    result = run_case(service, reference_model(case), case)
    failed = [(c.metric, c.reason) for c in result.checks if c.passed is False]
    assert not failed, failed
    assert case_passed(result.checks) and result.run_status == "ok"


def test_policy_expectations_match_the_seed_data():
    desk = OrderDesk()
    assert desk.check_refund_policy(46, 20.00)["eligible"] is True     # H1
    assert desk.orders[49]["status"] == "shipped"                      # H2: address can change
    assert desk.check_refund_policy(43, 180.00)["eligible"] is False   # H7: over the limit
    assert desk.check_refund_policy(45, 75.00)["eligible"] is False    # H8: not delivered
