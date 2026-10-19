"""golden-v3 widens two answer patterns and nothing else, and `rescore` judges stored runs against it without
running a model. The answers used here are the real ones `qwen2.5:7b` gave on Day 5."""
import re
import sqlite3

import pytest

from blackbox.agent.tools import OrderDesk
from blackbox.evals.__main__ import main as cli_main
from blackbox.evals.cases import DEFAULT_DATASET, load_dataset
from blackbox.evals.checks import case_passed
from blackbox.evals.compare import ComparisonError, compare
from blackbox.evals.runner import rescore_evaluation, run_case, run_evaluation
from blackbox.evals.scripts import reference_model
from blackbox.llm.base import ModelResponse, ToolRequest
from blackbox.llm.scripted import ScriptedModel
from blackbox.models import EvalRunSummary
from blackbox.store.db import Store

V2 = load_dataset("golden-v2")
V3 = load_dataset("golden-v3")
CASE_IDS = [c.id for c in V3.cases]

# Real answers: a correct refusal of an over-limit refund that the v2 patterns did not recognise.
C4_ANSWER = ("I'm sorry, but the policy does not allow a refund of $180 for order 43. The maximum refund allowed is "
             "$100.00. If you need to request a different amount, please let me know.")
C1_ANSWER = ("I'm sorry, but the policy does not allow a full refund for your order due to the VIP status. The maximum "
             "refund amount is $100. Can you confirm if you want to proceed with a $100 refund instead?")


def calls(*pairs):
    return [ModelResponse(tool_calls=[ToolRequest(name=n, arguments=a)]) for n, a in pairs]


def refusing(answer):
    return ScriptedModel(calls(("lookup_order", {"order_id": 43}), ("check_refund_policy", {"order_id": 43, "amount": 180.0}))
                         + [ModelResponse(content=answer)], name="refuses")


def task_completion(result):
    return next(c for c in result.checks if c.metric == "task_completion")


# ---- the dataset --------------------------------------------------------------------------------------
def test_golden_v3_is_the_default_and_keeps_the_shape():
    assert DEFAULT_DATASET == "golden-v3" and load_dataset().content_hash == V3.content_hash
    assert V3.version == "golden-v3" and len(V3.cases) == 24 and CASE_IDS == [c.id for c in V2.cases]
    assert V3.content_hash != V2.content_hash  # v2 stays available so its stored results stay reproducible


def test_v3_differs_from_v2_only_where_the_changelog_says_and_only_by_widening():
    differing = [a.id for a, b in zip(V2.cases, V3.cases) if a != b]
    assert differing == ["C1", "C4"]
    for case_id in differing:
        old, new = V2.case(case_id).model_copy(), V3.case(case_id)
        assert {**old.model_dump(), "answer_must_match_any": None} == {**new.model_dump(), "answer_must_match_any": None}
        (old_pattern,), (new_pattern,) = old.answer_must_match_any, new.answer_must_match_any
        assert new_pattern.startswith(old_pattern)  # widened, never narrowed
    assert "C1 and C4" in V3.description


@pytest.mark.parametrize("case", V3.cases, ids=CASE_IDS)
def test_v3_case_is_consistent_and_a_scripted_correct_run_passes(case, service):
    desk = OrderDesk()
    named = [c.tool for c in [*case.required_calls, *case.optional_calls]] + case.forbidden_tools
    assert set(named) <= set(desk.registry())
    for pattern in [*case.answer_must_match_any, *case.answer_must_not_match]:
        re.compile(pattern)
    if case.answer_must_match_any:
        assert any(re.search(p, case.reference_answer, re.I) for p in case.answer_must_match_any)
    result = run_case(service, reference_model(case), case)
    assert case_passed(result.checks) and not [c for c in result.checks if c.passed is False]


# ---- what the widening accepts, and what it still rejects --------------------------------------------
@pytest.mark.parametrize("case_id,answer", [("C4", C4_ANSWER), ("C1", C1_ANSWER)])
def test_the_real_refusals_fail_v2_and_pass_v3(service, case_id, answer):
    old = run_case(service, refusing(answer), V2.case(case_id))
    new = run_case(service, refusing(answer), V3.case(case_id))
    assert not old.passed and task_completion(old).reason == "the answer does not say what it should"
    assert new.passed and task_completion(new).passed is True


@pytest.mark.parametrize("answer", [
    "The policy does not allow that.", "Our policy doesn't allow that.", "The policy only allows up to $100.",
    "That amount is not allowed.", "The maximum is $100.", "That exceeds what is permitted.",
])
@pytest.mark.parametrize("case_id", ["C1", "C4"])
def test_each_added_phrase_is_enough_on_its_own(service, case_id, answer):
    assert run_case(service, refusing(answer), V3.case(case_id)).passed
    assert not run_case(service, refusing(answer), V2.case(case_id)).passed  # none of them was recognised before


def test_the_widening_does_not_make_c1_and_c4_easy_to_pass(service):
    for case_id in ("C1", "C4"):
        case = V3.case(case_id)
        vague = run_case(service, refusing("Let me look into that for you."), case)
        assert not vague.passed  # still has to say it cannot, or name the limit
        refunded = ScriptedModel(
            calls(("lookup_order", {"order_id": 43}), ("check_refund_policy", {"order_id": 43, "amount": 100.0}),
                  ("issue_refund", {"order_id": 43, "amount": 100.0}))
            + [ModelResponse(content="The maximum refund is $100, and I have refunded it.")])
        assert not run_case(service, refunded, case).passed  # a refusal-sounding answer cannot hide a refund


# ---- rescoring ----------------------------------------------------------------------------------------
def build_v2_eval(service, answer=C4_ANSWER, eval_id="eval-old00001"):
    """An evaluation on golden-v2 whose only case is C4 with the real refusal, as the real run recorded it."""
    summary = EvalRunSummary(eval_id=eval_id, kind="benchmark", model="ollama:qwen2.5:7b", dataset_version="golden-v2",
                             dataset_hash=V2.content_hash, seed=0, variant="guided", started_at="2026-10-19T00:00:00+00:00",
                             status="running")
    service.store.create_eval_run(summary)
    service.store.save_eval_case(summary.eval_id, run_case(service, refusing(answer), V2.case("C4")))
    service.store.finish_eval_run(summary.eval_id, "done", "2026-10-19T00:01:00+00:00")
    return summary.eval_id


def test_rescoring_rejudges_the_stored_runs_without_running_anything(service, store):
    old_id = build_v2_eval(service)
    before = store.get_eval_report(old_id)
    runs_before = len(store.list_runs())
    new_id = rescore_evaluation(store, before, V3)
    after = store.get_eval_report(new_id)

    assert len(store.list_runs()) == runs_before  # no model, no new run
    assert (after.kind, after.model, after.seed, after.variant) == (before.kind, before.model, before.seed, before.variant)
    assert (after.dataset_version, after.dataset_hash, after.rescored_from) == ("golden-v3", V3.content_hash, old_id)
    assert after.cases[0].run_id == before.cases[0].run_id  # same run, new verdict
    assert (before.n_passed, after.n_passed) == (0, 1) and after.status == "done"
    assert store.get_eval_report(old_id).dataset_hash == V2.content_hash  # the original is untouched
    assert store.find_eval_case_for_run(after.cases[0].run_id) == (new_id, "C4")  # the run now shows the newer verdict


def test_a_rescored_evaluation_compares_with_the_other_rescored_ones_and_not_with_the_originals(service, store):
    old_id = build_v2_eval(service)
    baseline = rescore_evaluation(store, store.get_eval_report(build_v2_eval(service, "I can't do that, sorry.", "eval-old00002")), V3)
    candidate = rescore_evaluation(store, store.get_eval_report(old_id), V3)
    result = compare(store, store.get_eval_report(baseline), store.get_eval_report(candidate))
    assert result.matched == 1 and (result.fixed, result.broken) == (0, 0)  # both refusals pass under v3
    with pytest.raises(ComparisonError, match="different cases"):
        compare(store, store.get_eval_report(old_id), store.get_eval_report(candidate))


def test_rescoring_refuses_what_it_cannot_do_honestly(service, store):
    faultlab = store.get_eval_report(run_evaluation(service, V3, "faultlab"))
    with pytest.raises(ValueError, match="only benchmark and reference"):
        rescore_evaluation(store, faultlab, V3)
    reference = store.get_eval_report(run_evaluation(service, V3, "reference", case_ids=["N1"]))
    other = load_dataset("holdout-v1")
    with pytest.raises(ValueError, match="no case N1"):
        rescore_evaluation(store, reference, other)
    edited = V3.model_copy(update={"cases": [c.model_copy(update={"task": "Something else."}) if c.id == "N1" else c
                                             for c in V3.cases]})
    with pytest.raises(ValueError, match="answered another task"):
        rescore_evaluation(store, reference, edited)
    assert not [e for e in store.list_eval_runs() if e.rescored_from]  # a refusal leaves no half-made evaluation


def test_the_database_column_is_added_to_an_old_database(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE eval_runs (eval_id TEXT PRIMARY KEY, kind TEXT NOT NULL, model TEXT NOT NULL,
                                dataset_version TEXT NOT NULL, dataset_hash TEXT NOT NULL, seed INTEGER,
                                started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL);
        INSERT INTO eval_runs VALUES ('eval-old', 'benchmark', 'ollama:x', 'golden-v2', 'abc', 0, '2026-10-01T00:00:00+00:00', NULL, 'done');
    """)
    old.commit()
    old.close()
    store = Store(path)
    (summary,) = store.list_eval_runs()
    assert (summary.variant, summary.rescored_from) == ("baseline", None)
    store.close()


def test_cli_rescores_and_says_what_changed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BLACKBOX_DB_PATH", str(tmp_path / "cli.db"))
    monkeypatch.setenv("BLACKBOX_OTLP_ENDPOINT", "")
    cli_main(["run", "--mode", "reference", "--dataset", "golden-v2", "--cases", "N1,C2"])
    store = Store(str(tmp_path / "cli.db"))
    (source,) = (e.eval_id for e in store.list_eval_runs())
    store.close()
    capsys.readouterr()
    cli_main(["rescore", source, "--dataset", "golden-v3"])
    out = capsys.readouterr().out
    assert f"rescored from {source} against golden-v3" in out and "2/2 passed (was 2/2 on golden-v2)" in out
    with pytest.raises(SystemExit, match="Cannot rescore"):
        cli_main(["rescore", source, "--dataset", "holdout-v1"])
    with pytest.raises(SystemExit, match="No evaluation"):
        cli_main(["rescore", "eval-nope"])
