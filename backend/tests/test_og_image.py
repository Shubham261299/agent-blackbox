"""The card that shows when the demo's link is shared: right size, figures from the data, committed and in the build."""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("make_og_image", ROOT / "scripts" / "make_og_image.py")
og = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(og)

DATA = ROOT / "frontend" / "public" / "demo-data"
needs_data = pytest.mark.skipif(not DATA.exists(), reason="demo data not exported")


@needs_data
def test_the_three_results_on_the_card_are_the_stored_comparisons():
    assert og.facts() == [
        ("Found the step", "that made a run fail"),
        ("3 of 4", "problems fixed by retrying"),
        ("Fixed 2, broke 5", "by rewriting the instructions"),
    ]


@needs_data
def test_changing_the_data_changes_the_card(tmp_path):
    shutil.copytree(DATA, tmp_path / "data")
    tour = json.loads((tmp_path / "data" / "manifest.json").read_text(encoding="utf-8"))["tour"]
    index = json.loads((tmp_path / "data" / "comparisons" / "index.json").read_text(encoding="utf-8"))["ok"]
    for pair, field, value in ((tour["fixed"], "fixed", 1), (tour["regressed"], "broken", 9)):
        path = tmp_path / "data" / "comparisons" / index[f"{pair[0]}|{pair[1]}"]
        comparison = json.loads(path.read_text(encoding="utf-8"))
        comparison[field] = value
        path.write_text(json.dumps(comparison), encoding="utf-8")
    facts = og.facts(tmp_path / "data")
    assert facts[1][0] == "1 of 4" and facts[2][0] == "Fixed 2, broke 9"


@needs_data
def test_the_card_is_1200_by_630_with_the_headline_and_three_boxes(tmp_path):
    out = tmp_path / "og.png"
    assert og.main(["--out", str(out)]) == 0
    with Image.open(out) as img:
        assert img.size == (1200, 630)
        assert img.getpixel((5, 5)) == og.BG
        # three boxes along the bottom, each lighter than the background
        assert all(img.getpixel((x, 500)) != og.BG for x in (200, 600, 1000))
        assert img.getpixel((50, 500)) == og.BG  # and nothing outside them


@needs_data
def test_the_headline_fits_in_three_lines():
    from PIL import ImageDraw

    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    assert len(og.wrap(d, og.HEADLINE, og.font(58), og.SIZE[0] - 128)) <= 3


def test_the_committed_card_is_the_size_the_page_declares_and_small_enough():
    path = ROOT / "frontend" / "public" / "og.png"
    if not path.exists():
        pytest.skip("card not generated")
    assert path.stat().st_size < 300_000
    with Image.open(path) as img:
        assert img.size == (1200, 630)
    meta = (ROOT / "frontend" / "src" / "lib" / "demoMeta.ts").read_text(encoding="utf-8")
    assert "width: 1200, height: 630" in meta and 'og.png' in meta
