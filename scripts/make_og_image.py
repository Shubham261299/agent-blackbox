"""Makes frontend/public/og.png: the 1200 x 630 card that shows when the demo's link is pasted into LinkedIn, a chat or an email.

    python scripts/make_og_image.py          # needs Pillow (pip install -e ".[dev]")

The three results on the card are read from the baked demo data, never typed here.
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_demo_gif import DEMO_DATA, font, load, wrap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "og.png"
SIZE = (1200, 630)
BG, INK, MUTED, ORANGE, CARD = (18, 23, 27), (243, 245, 244), (150, 160, 168), (242, 106, 27), (27, 33, 39)
HEADLINE = "AI agents can fail without anyone noticing. I built a flight recorder that shows where."


def facts(data_dir: Path = DEMO_DATA) -> list[tuple[str, str]]:
    """(big text, small text) for each of the three results, from the baked comparisons."""
    tour = load("manifest.json", data_dir)["tour"]
    index = load("comparisons/index.json", data_dir)["ok"]

    def comparison(pair):
        return load("comparisons/" + index[f"{pair[0]}|{pair[1]}"], data_dir)

    lab, bench = comparison(tour["fixed"]), comparison(tour["regressed"])
    return [
        ("Found the step", "that made a run fail"),
        (f"{lab['fixed']} of {lab['matched']}", "problems fixed by retrying"),
        (f"Fixed {bench['fixed']}, broke {bench['broken']}", "by rewriting the instructions"),
    ]


def draw_card(data_dir: Path = DEMO_DATA) -> Image.Image:
    img = Image.new("RGB", SIZE, BG)
    d = ImageDraw.Draw(img)
    # the brand mark: three bars of a tiny trace waterfall on an orange tile
    d.rounded_rectangle((64, 56, 120, 112), radius=12, fill=ORANGE)
    for (x0, y0, x1) in ((76, 71, 108), (76, 82, 96), (84, 93, 108)):
        d.rounded_rectangle((x0, y0, x1, y0 + 7), radius=3, fill=(255, 255, 255))
    d.text((140, 62), "Agent Blackbox", font=font(34), fill=INK)
    d.text((140, 102), "A recorded demo with real results", font=font(22), fill=MUTED)

    big = font(58)
    y = 180
    for line in wrap(d, HEADLINE, big, SIZE[0] - 128)[:3]:
        d.text((64, y), line, font=big, fill=INK)
        y += 72

    x, top, w, h, gap = 64, 430, 345, 140, 20
    for headline, small in facts(data_dir):
        d.rounded_rectangle((x, top, x + w, top + h), radius=14, fill=CARD, outline=(54, 64, 74))
        face = font(36)
        text = headline
        while d.textlength(text, font=face) > w - 36 and face.size > 22:
            face = font(face.size - 2)
        d.text((x + 18, top + 22), text, font=face, fill=INK)
        d.text((x + 18, top + 84), small, font=font(22), fill=MUTED)
        x += w + gap
    return img


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    draw_card().save(args.out, optimize=True)
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
