"""The README quotes numbers and links into the demo. They are checked against the data the demo is built from, so
a re-export (or an edit of the README) that makes them disagree fails here instead of reaching a reader."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
DEMO = ROOT / "frontend" / "public" / "demo-data"
EVAL_ID = re.compile(r"eval-[0-9a-f]{8}")

pytestmark = pytest.mark.skipif(not (README.exists() and DEMO.exists()), reason="README or demo data not present")


def load(name):
    return json.loads((DEMO / name).read_text(encoding="utf-8"))


def passed(eval_id):
    cases = load(f"evals/{eval_id}.json")["cases"]
    return sum(1 for c in cases if c["passed"]), len(cases)


def comparison(before, after):
    return load("comparisons/" + load("comparisons/index.json")["ok"][f"{before}|{after}"])


def rows():
    return [line for line in README.read_text(encoding="utf-8").splitlines() if line.startswith("|") and EVAL_ID.search(line)]


def test_every_evaluation_the_readme_names_is_in_the_demo():
    known = {e["eval_id"] for e in load("evals.json")}
    named = set(EVAL_ID.findall(README.read_text(encoding="utf-8")))
    assert named and named <= known, named - known


def test_each_single_evaluation_row_states_the_pass_count_that_evaluation_has():
    checked = 0
    for line in rows():
        ids = EVAL_ID.findall(line)
        claim = re.search(r"(\d+) of (\d+)", line)
        if len(ids) == 1 and claim:
            assert (int(claim[1]), int(claim[2])) == passed(ids[0]), line
            checked += 1
    assert checked == 4  # baseline, retrying, and the two rewrites of the instructions


def test_the_held_out_row_says_five_of_eight_and_each_one_is():
    (line,) = [r for r in rows() if "Held-out" in r]
    assert "5 of 8 each" in line
    for eval_id in EVAL_ID.findall(line):
        assert passed(eval_id) == (5, 8)


def test_the_before_and_after_counts_in_the_readme_are_the_comparisons():
    text = README.read_text(encoding="utf-8")
    ids = {"baseline": "eval-09d327ad", "resilient": "eval-b07a0e6d", "v2": "eval-71224f4b", "v3": "eval-c45fdf03"}
    for name, expected in (("resilient", (0, 0)), ("v2", (2, 5)), ("v3", (1, 3))):
        c = comparison(ids["baseline"], ids[name])
        assert (c["fixed"], c["broken"]) == expected
        assert f"{expected[0]} fixed, {expected[1]} broken" in text, name
    lab = comparison("eval-7f1699f1", "eval-0f9152b9")
    assert (lab["fixed"], lab["broken"], lab["matched"]) == (3, 0, 4)
    assert (lab["baseline_cost"]["retries"], lab["candidate_cost"]["retries"]) == (0, 3)
    assert (lab["baseline_cost"]["tool_calls"], lab["candidate_cost"]["tool_calls"]) == (11, 13)
    for sentence in ("3 faults fixed, 0 broken, 3 extra retries (11 to 13 tool calls)", "Of the four problems", "three now have no effect on the run and none got worse"):
        assert sentence in text, sentence
    assert "fixed 2 and broke 5" in text


def test_links_into_the_demo_point_at_runs_and_comparisons_that_exist():
    text = README.read_text(encoding="utf-8")
    runs = {r["run_id"] for r in load("runs.json")}
    ok = load("comparisons/index.json")["ok"]
    links = re.findall(r"shubham261299\.github\.io/agent-blackbox/#/(runs|compare)/([\w-]+)(?:/([\w-]+))?", text)
    assert len(links) == 3
    tour = load("manifest.json")["tour"]  # the same three stops as the demo's "Start here" card, before first
    assert {(k, a, b) for k, a, b in links} == {("runs", tour["failed_run"], ""), ("compare", *tour["fixed"]), ("compare", *tour["regressed"])}
    for kind, first, second in links:
        if kind == "runs":
            assert first in runs
        else:
            assert f"{first}|{second}" in ok


def test_the_images_the_readme_shows_exist():
    text = README.read_text(encoding="utf-8")
    markdown_images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    html_images = re.findall(r'<img\b[^>]*\bsrc=["\x27]([^"\x27]+)["\x27]', text, flags=re.IGNORECASE)
    paths = {p for p in markdown_images + html_images if not p.startswith(("http://", "https://"))}
    # Keep the original evidence visible, while allowing new covers and charts.
    required = {
        "docs/images/demo.gif",
        "docs/images/failed-run.png",
        "docs/images/fix-that-worked.png",
        "docs/images/fix-that-did-not.png",
    }
    assert required <= paths, required - paths
    for path in paths:
        assert (ROOT / path).is_file(), path
