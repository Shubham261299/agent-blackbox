"""The golden dataset must be internally consistent, and a scripted correct run of every case must pass
every check. If this fails, either the dataset or a check is wrong; the agent is not involved."""
import re
from collections import Counter

import pytest

from blackbox.agent.tools import OrderDesk
from blackbox.evals.cases import load_dataset
from blackbox.evals.checks import case_passed
from blackbox.evals.runner import run_case
from blackbox.evals.scripts import reference_model

DATASET = load_dataset("golden-v2")  # frozen: golden-v3 has its own tests (test_eval_golden_v3.py)
CASE_IDS = [c.id for c in DATASET.cases]
KNOWN_TOOLS = set(OrderDesk().registry())
NONEXISTENT_ORDER_CASES = {"F1", "F4"}  # these two are about orders that do not exist, on purpose


def test_dataset_shape():
    assert DATASET.version == "golden-v2" and len(DATASET.content_hash) == 12
    assert len(DATASET.cases) == 24 and len(set(CASE_IDS)) == 24
    assert Counter(c.category for c in DATASET.cases) == {
        "normal": 8, "ambiguous": 4, "wrong_tool": 4, "tool_failure": 4, "constraint": 4}


def test_v2_differs_from_v1_only_where_the_changelog_says():
    v1 = load_dataset("golden-v1")
    assert v1.content_hash != DATASET.content_hash  # v1 stays available so its stored results stay reproducible
    differing = [a.id for a, b in zip(v1.cases, DATASET.cases) if a != b]
    assert [c.id for c in v1.cases] == CASE_IDS and differing == ["F1", "C2"]
    for case_id in differing:  # widened, never narrowed: every v1 pattern is still in v2
        old, new = v1.case(case_id).answer_must_match_any, DATASET.case(case_id).answer_must_match_any
        assert all(any(o in n for n in new) for o in old)
    assert "F1 and C2" in DATASET.description


def test_hash_identifies_the_content():
    assert load_dataset("golden-v2").content_hash == DATASET.content_hash


@pytest.mark.parametrize("case", DATASET.cases, ids=CASE_IDS)
def test_case_references_real_tools_and_orders(case):
    desk = OrderDesk()
    named = [c.tool for c in [*case.required_calls, *case.optional_calls]] + case.forbidden_tools
    assert set(named) <= KNOWN_TOOLS
    assert not set(c.tool for c in [*case.required_calls, *case.optional_calls]) & set(case.forbidden_tools)
    ids = [c.args.get("order_id") for c in [*case.required_calls, *case.optional_calls]]
    ids += [r.order_id for r in case.outcome.refunds] + [a.order_id for a in case.outcome.address_changes]
    if case.id not in NONEXISTENT_ORDER_CASES:
        assert all(i in desk.orders for i in ids if i is not None)
    assert case.optimal_tool_calls >= len(case.required_calls)
    for pattern in [*case.answer_must_match_any, *case.answer_must_not_match]:
        re.compile(pattern)


@pytest.mark.parametrize("case", DATASET.cases, ids=CASE_IDS)
def test_reference_answer_satisfies_its_own_patterns(case):
    answer = case.reference_answer
    if case.answer_must_match_any:
        assert any(re.search(p, answer, re.I) for p in case.answer_must_match_any)
    assert not any(re.search(p, answer, re.I) for p in case.answer_must_not_match)


@pytest.mark.parametrize("case", DATASET.cases, ids=CASE_IDS)
def test_scripted_correct_run_passes_every_check(case, service):
    result = run_case(service, reference_model(case), case)
    failed = [(c.metric, c.reason) for c in result.checks if c.passed is False]
    assert not failed, failed
    assert case_passed(result.checks) and result.run_status == "ok"


def test_policy_boundaries_in_the_seed_data_match_the_dataset_intent():
    desk = OrderDesk()
    assert desk.check_refund_policy(47, 100.00)["eligible"] is True    # N3: exactly at the limit, day 29
    assert desk.check_refund_policy(48, 100.01)["eligible"] is False   # N5: one cent over
    assert desk.check_refund_policy(43, 180.00)["eligible"] is False   # N4
    assert desk.check_refund_policy(44, 40.00)["eligible"] is False    # C3: 45 days
    assert desk.check_refund_policy(45, 75.00)["eligible"] is False    # F3: not delivered
    assert desk.check_refund_policy(46, 20.00)["eligible"] is True     # N2
    assert desk.check_refund_policy(42, 25.00)["eligible"] is True     # N8
