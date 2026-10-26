"""The script that makes docs/images/demo.gif: captions come from the data, frames are composed as intended, and the
browser step (which needs Edge or Chrome) is checked with a stand-in browser."""
import importlib.util
import json
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PIL")
from PIL import Image, ImageSequence  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("make_demo_gif", ROOT / "scripts" / "make_demo_gif.py")
gif = importlib.util.module_from_spec(SPEC)
sys.modules["make_demo_gif"] = gif
SPEC.loader.exec_module(gif)

DATA = ROOT / "frontend" / "public" / "demo-data"
needs_data = pytest.mark.skipif(not DATA.exists(), reason="demo data not exported")


def screenshot(width=1280, height=900, colour=(238, 241, 240)):
    return Image.new("RGB", (width, height), colour)


# ---- captions and routes --------------------------------------------------------------------------------
@needs_data
def test_the_walk_through_has_six_frames_each_with_a_caption_that_fits():
    specs = gif.frames()
    assert [s.route.split("/")[0] for s in specs] == ["", "runs", "runs", "compare", "compare", "compare"]
    for i, spec in enumerate(specs, start=1):
        gif.caption_frame(screenshot(height=spec.window_height), spec.caption, f"{i} / 6", spec.top)  # raises if too long


@needs_data
def test_the_numbers_in_the_captions_are_the_ones_in_the_data():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    captions = [s.caption for s in gif.frames()]
    assert f"holds {manifest['counts']['runs']} real runs" in captions[0]
    assert "3 of 4 planted faults no longer matter, and 0 got worse" in captions[3]
    assert "On 24 cases it fixed 2 and broke 5" in captions[4]


@needs_data
def test_the_routes_are_the_tour_and_the_unfair_pair_is_really_refused():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    tour = manifest["tour"]
    specs = gif.frames()
    assert specs[1].route == specs[2].route == f"runs/{tour['failed_run']}"
    # the trace is below the first screen, so its frame scrolls down and the window is tall enough to hold it
    assert specs[1].top == 0 and specs[2].top >= 500 and specs[2].window_height >= specs[2].top + gif.VIEW[1]
    assert specs[3].route == "compare/{}/{}".format(*tour["fixed"])
    assert specs[4].route == "compare/{}/{}".format(*tour["regressed"])
    _, before, after = specs[5].route.split("/")
    assert "different cases" in json.loads((DATA / "comparisons" / "index.json").read_text(encoding="utf-8"))["refused"][f"{before}|{after}"]


@needs_data
def test_changing_the_data_changes_the_captions(tmp_path):
    shutil.copytree(DATA, tmp_path / "data")
    manifest_path = tmp_path / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["runs"] = 4242
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    index = json.loads((tmp_path / "data" / "comparisons" / "index.json").read_text(encoding="utf-8"))["ok"]
    for key, field, value in ((f"{manifest['tour']['fixed'][0]}|{manifest['tour']['fixed'][1]}", "fixed", 1),
                              (f"{manifest['tour']['regressed'][0]}|{manifest['tour']['regressed'][1]}", "broken", 9)):
        path = tmp_path / "data" / "comparisons" / index[key]
        comparison = json.loads(path.read_text(encoding="utf-8"))
        comparison[field] = value
        path.write_text(json.dumps(comparison), encoding="utf-8")
    captions = [s.caption for s in gif.frames(tmp_path / "data")]
    assert "holds 4242 real runs" in captions[0]
    assert "1 of 4 planted faults no longer matter" in captions[3]
    assert "it fixed 2 and broke 9" in captions[4]


# ---- composing a frame ----------------------------------------------------------------------------------
def test_a_frame_is_the_gif_size_with_a_dark_caption_band_and_the_page_above_it():
    out = gif.caption_frame(screenshot(colour=(238, 241, 240)), "A short caption.", "1 / 6")
    assert out.size == gif.SIZE
    scale = gif.SIZE[0] / gif.VIEW[0]
    band_top = int((gif.VIEW[1] - gif.BAND) * scale)
    assert out.getpixel((5, 5)) == (238, 241, 240)                  # the page, untouched
    assert sum(out.getpixel((900, band_top + 2))) < 100             # the band
    assert sum(out.getpixel((5, gif.SIZE[1] - 2))) < 100
    assert any(sum(out.getpixel((x, y))) > 600 for x in range(20, 400) for y in range(band_top + 8, band_top + 55))  # caption text is drawn


def test_the_caption_is_drawn_on_top_of_the_part_of_the_page_that_was_asked_for():
    shot = screenshot(height=1500)
    for y in range(1500):
        shot.paste((200, 0, 0) if y >= 600 else (0, 0, 200), (0, y, 1280, y + 1))
    assert gif.caption_frame(shot, "x", "1 / 1", top=0).getpixel((5, 5))[2] > 150          # still blue
    assert gif.caption_frame(shot, "x", "1 / 1", top=700).getpixel((5, 5))[0] > 150       # cropped to the red part


def test_a_screenshot_shorter_than_asked_is_padded_not_stretched():
    out = gif.caption_frame(screenshot(height=300, colour=(10, 200, 10)), "x", "1 / 1")
    assert out.getpixel((5, 5))[1] > 150 and out.getpixel((5, 400)) == (238, 241, 240)


def test_a_caption_that_needs_three_lines_is_refused_instead_of_cut_off():
    from PIL import ImageDraw

    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    words = ["word"]
    while len(gif.wrap(draw, " ".join(words), gif.font(30), gif.VIEW[0] - 150)) < 3:
        words.append("word")
    assert len(gif.wrap(draw, " ".join(words), gif.font(30), gif.VIEW[0] - 150)) == 3  # the smallest caption that is too long
    with pytest.raises(ValueError, match="at most 2"):
        gif.caption_frame(screenshot(), " ".join(words), "1 / 1")
    gif.caption_frame(screenshot(), " ".join(words[:-8]), "1 / 1")  # two lines are fine


def test_wrapping_never_exceeds_the_width_and_keeps_every_word():
    from PIL import ImageDraw

    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    face = gif.font(30)
    text = "Every step an AI agent takes is recorded and then checked against plain questions"
    lines = gif.wrap(draw, text, face, 600)
    assert len(lines) > 1 and " ".join(lines) == text
    assert all(draw.textlength(line, font=face) <= 600 for line in lines)
    assert gif.wrap(draw, "", face, 600) == []


# ---- writing the gif ------------------------------------------------------------------------------------
def test_the_gif_has_every_frame_loops_and_holds_the_first_one_a_little_longer(tmp_path):
    images = [gif.caption_frame(screenshot(colour=(i * 30, 100, 100)), f"frame {i}", f"{i} / 3") for i in range(3)]
    out = tmp_path / "sub" / "demo.gif"
    gif.write_gif(images, out, seconds=2)
    with Image.open(out) as g:
        assert g.size == gif.SIZE and g.info["loop"] == 0 and g.n_frames == 3
        durations = [f.info["duration"] for f in ImageSequence.Iterator(g)]
    assert durations == [2500, 2000, 2000]


# ---- the browser ----------------------------------------------------------------------------------------
def test_an_explicit_browser_is_used_if_it_exists_and_never_silently_replaced(tmp_path):
    exe = tmp_path / "browser.exe"
    exe.write_text("x")
    assert gif.find_browser([], {"BLACKBOX_BROWSER": str(exe)}) == str(exe)
    assert gif.find_browser([str(exe)], {"BLACKBOX_BROWSER": str(tmp_path / "missing")}) is None


def test_the_first_installed_candidate_wins(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_text("x")
    b.write_text("x")
    assert gif.find_browser([str(tmp_path / "none"), str(a), str(b)], {}) == str(a)


def test_capture_asks_for_a_private_profile_and_waits_for_a_late_screenshot(tmp_path, monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        out = Path(next(c for c in cmd if c.startswith("--screenshot=")).split("=", 1)[1])
        threading.Timer(0.6, lambda: screenshot(10, 10).save(out)).start()  # written after the launcher has returned

        class Done:
            returncode = 0

        return Done()

    monkeypatch.setattr(gif.subprocess, "run", fake_run)
    out = tmp_path / "shot.png"
    gif.capture("browser", "http://127.0.0.1:1/x", 1280, 900, out, tmp_path / "profile")
    assert out.is_file() and out.stat().st_size > 0
    cmd = seen["cmd"]
    assert f"--user-data-dir={tmp_path / 'profile'}" in cmd and "--window-size=1280,900" in cmd and "--headless" in cmd
    assert cmd[-1] == "http://127.0.0.1:1/x"


def test_capture_gives_up_with_a_clear_error_when_no_screenshot_ever_appears(tmp_path, monkeypatch):
    monkeypatch.setattr(gif.subprocess, "run", lambda *a, **k: None)
    clock = iter(range(0, 10_000, 20))
    monkeypatch.setattr(gif.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(gif.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="no screenshot for http://x"):
        gif.capture("browser", "http://x", 10, 10, tmp_path / "never.png", tmp_path / "p")


# ---- the whole build ------------------------------------------------------------------------------------
@needs_data
def test_build_serves_the_site_captures_every_frame_and_cleans_up(tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html></html>", encoding="utf-8")
    urls = []

    def fake_capture(browser, url, width, height, out, profile):
        urls.append((url, width, height))
        screenshot(width, height).save(out)

    monkeypatch.setattr(gif, "capture", fake_capture)
    before = set(Path(gif.tempfile.gettempdir()).glob("blackbox-gif-*"))
    out = gif.build(site, tmp_path / "out" / "demo.gif", DATA, browser="fake")
    assert len(urls) == 6 and urls[0][0].endswith("/index.html#/") and "#/runs/" in urls[1][0] and "#/compare/" in urls[5][0]
    assert urls[2][1:] == (1280, 1330)
    with Image.open(out) as g:
        assert g.n_frames == 6
    assert set(Path(gif.tempfile.gettempdir()).glob("blackbox-gif-*")) == before


@needs_data
def test_build_explains_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(gif, "find_browser", lambda *a, **k: None)
    with pytest.raises(SystemExit, match="No Edge or Chrome"):
        gif.build(tmp_path, tmp_path / "x.gif", DATA)
    with pytest.raises(SystemExit, match="npm run build:demo"):
        gif.build(tmp_path / "unbuilt", tmp_path / "x.gif", DATA, browser="fake")


def test_the_committed_gif_is_small_and_has_the_six_frames():
    committed = ROOT / "docs" / "images" / "demo.gif"
    if not committed.exists():
        pytest.skip("gif not generated")
    assert committed.stat().st_size < 1_000_000
    with Image.open(committed) as g:
        assert g.n_frames == 6 and g.size == gif.SIZE and g.info["loop"] == 0
    assert time.time() > 0


def test_main_also_puts_the_gif_where_the_demo_site_picks_it_up(tmp_path, monkeypatch):
    def fake_build(site, out, *args, **kwargs):
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"GIF89a-test")
        return out

    monkeypatch.setattr(gif, "build", fake_build)
    out, copy = tmp_path / "docs" / "demo.gif", tmp_path / "site" / "public" / "tour.gif"
    assert gif.main(["--out", str(out), "--site-copy", str(copy)]) == 0
    assert copy.read_bytes() == out.read_bytes() == b"GIF89a-test"


def test_the_committed_site_copy_is_the_same_gif_as_the_readmes():
    docs, site = ROOT / "docs" / "images" / "demo.gif", ROOT / "frontend" / "public" / "tour.gif"
    if not (docs.exists() and site.exists()):
        pytest.skip("gif not generated")
    assert docs.read_bytes() == site.read_bytes()
