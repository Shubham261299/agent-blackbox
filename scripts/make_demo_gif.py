"""Makes docs/images/demo.gif: a captioned walk through the recorded demo, from real screenshots of the built site.

    cd frontend && npm run build:demo        # once, and after any change to the UI or the data
    python scripts/make_demo_gif.py          # needs Pillow (pip install -e ".[dev]") and Edge or Chrome

Every number in a caption is read from the same files the demo shows (frontend/public/demo-data), never typed here.
Nothing is uploaded: the site is served from a throwaway local server and screenshotted in a headless browser.
"""
import argparse
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DEMO_DATA = ROOT / "frontend" / "public" / "demo-data"
SITE = ROOT / "frontend" / "dist-demo"
OUT = ROOT / "docs" / "images" / "demo.gif"

VIEW = (1280, 720)         # what is shown of each page
SIZE = (960, 540)          # the GIF's size
BAND = 92                  # height of the caption band at VIEW size
SECONDS = 4.0
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/usr/bin/microsoft-edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
FONTS = [
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


class Frame:
    """One page of the demo: where it is, how big a window shows all that is wanted, and which part to keep."""

    def __init__(self, route: str, caption: str, window_height: int = 720, top: int = 0):
        self.route, self.caption, self.window_height, self.top = route, caption, window_height, top


def load(name: str, data_dir: Path = DEMO_DATA):
    return json.loads((data_dir / name).read_text(encoding="utf-8"))


def frames(data_dir: Path = DEMO_DATA) -> list[Frame]:
    """The walk-through, with every figure taken from the baked data."""
    manifest = load("manifest.json", data_dir)
    index = load("comparisons/index.json", data_dir)
    tour = manifest["tour"]

    def comparison(pair):
        return load("comparisons/" + index["ok"][f"{pair[0]}|{pair[1]}"], data_dir)

    lab, bench = comparison(tour["fixed"]), comparison(tour["regressed"])
    unfair = next(key for key, reason in index["refused"].items() if "different cases" in reason)
    before, after = unfair.split("|")
    return [
        Frame("", f"Every step an AI agent takes is recorded. This demo holds {manifest['counts']['runs']} real runs."),
        Frame(f"runs/{tour['failed_run']}", "A tool timed out and the run failed. The page says which step to look at first."),
        Frame(f"runs/{tour['failed_run']}", "The failed step is red in the trace, next to the error that caused it.", 1330, 610),
        Frame(f"compare/{tour['fixed'][0]}/{tour['fixed'][1]}",
              f"Retrying failed steps: {lab['fixed']} of {lab['matched']} planted faults no longer matter, and {lab['broken']} got worse."),
        Frame(f"compare/{tour['regressed'][0]}/{tour['regressed'][1]}",
              f"A rewritten prompt looked like an improvement. On {bench['matched']} cases it fixed {bench['fixed']} and broke {bench['broken']}."),
        Frame(f"compare/{before}/{after}", "The page refuses to compare runs that tested different things, and says why."),
    ]


# ---- the browser ----------------------------------------------------------------------------------------
def find_browser(candidates: Iterable[str] = BROWSERS, env: dict[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
    chosen = env.get("BLACKBOX_BROWSER")
    if chosen:
        return chosen if Path(chosen).is_file() else None
    for path in candidates:
        if Path(path).is_file():
            return path
    for name in ("microsoft-edge", "msedge", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    return None


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401 - keep the console for the one useful line
        pass


def serve(site: Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def capture(browser: str, url: str, width: int, height: int, out: Path, profile: Path) -> None:
    """Screenshot `url` into `out`. `profile` is a private folder for the browser's settings, kept until all captures
    are done: without one, a browser that is already open on this machine takes the request over, and some builds
    return at once and write the file a moment later from a process that still needs that folder."""
    subprocess.run(
        [browser, "--headless", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}", f"--window-size={width},{height}",
         "--virtual-time-budget=8000", f"--screenshot={out}", url],
        check=True, capture_output=True, timeout=120)
    deadline = time.monotonic() + 60
    while not (out.is_file() and out.stat().st_size > 0):
        if time.monotonic() > deadline:
            raise RuntimeError(f"the browser produced no screenshot for {url}")
        time.sleep(0.25)
    time.sleep(0.5)  # let the writer finish


# ---- composing ------------------------------------------------------------------------------------------
def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONTS:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def wrap(draw: ImageDraw.ImageDraw, text: str, face, width: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and draw.textlength(trial, font=face) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line] if line else lines


def caption_frame(shot: Image.Image, caption: str, position: str, top: int = 0) -> Image.Image:
    """Crop the screenshot to VIEW, put the caption on a band at the bottom, shrink to SIZE."""
    shot = shot.convert("RGB")
    # Crop inside the screenshot and paste onto the page colour: cropping past its edge would fill with black.
    view = Image.new("RGB", VIEW, (238, 241, 240))
    view.paste(shot.crop((0, top, min(shot.width, VIEW[0]), min(shot.height, top + VIEW[1]))), (0, 0))
    draw = ImageDraw.Draw(view)
    draw.rectangle((0, VIEW[1] - BAND, VIEW[0], VIEW[1]), fill=(18, 23, 27))
    face, small = font(30), font(20)
    lines = wrap(draw, caption, face, VIEW[0] - 150)
    if len(lines) > 2:
        raise ValueError(f"caption needs {len(lines)} lines, at most 2 fit: {caption!r}")
    y = VIEW[1] - BAND + (BAND - 38 * len(lines)) // 2
    for line in lines:
        draw.text((32, y), line, font=face, fill=(243, 245, 244))
        y += 38
    draw.text((VIEW[0] - 32 - draw.textlength(position, font=small), VIEW[1] - BAND + 30), position, font=small, fill=(138, 148, 157))
    return view.resize(SIZE, Image.LANCZOS)


def write_gif(images: Sequence[Image.Image], out: Path, seconds: float = SECONDS) -> None:
    palette = [im.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for im in images]
    durations = [int(seconds * 1000)] * len(palette)
    durations[0] += 500
    out.parent.mkdir(parents=True, exist_ok=True)
    palette[0].save(out, save_all=True, append_images=palette[1:], duration=durations, loop=0, optimize=True, disposal=1)


def build(site: Path = SITE, out: Path = OUT, data_dir: Path = DEMO_DATA, browser: str | None = None) -> Path:
    browser = browser or find_browser()
    if not browser:
        sys.exit("No Edge or Chrome found. Install one, or set BLACKBOX_BROWSER to its path.")
    if not (site / "index.html").is_file():
        sys.exit(f"{site} is not built. Run `npm run build:demo` in frontend/ first.")
    specs = frames(data_dir)
    server, port = serve(site)
    # A plain folder, not tempfile.mkdtemp(): on Windows that one is private to this process, and a browser that hands
    # the request to an already-running instance (which has another security context) then cannot write the screenshot.
    work = Path(tempfile.gettempdir()) / f"blackbox-gif-{os.getpid()}"
    work.mkdir(exist_ok=True)
    try:
        images = []
        for i, spec in enumerate(specs, start=1):
            shot = work / f"{i}.png"
            capture(browser, f"http://127.0.0.1:{port}/index.html#/{spec.route}", VIEW[0], spec.window_height, shot, work / "profile")
            with Image.open(shot) as raw:
                images.append(caption_frame(raw, spec.caption, f"{i} / {len(specs)}", spec.top))
    finally:
        server.shutdown()
        shutil.rmtree(work, ignore_errors=True)
    write_gif(images, out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--site", type=Path, default=SITE, help="the built demo (default: frontend/dist-demo)")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    out = build(args.site, args.out)
    print(f"wrote {out} ({out.stat().st_size // 1024} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
