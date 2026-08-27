"""Assemble the demo video from the captured stills.

    python scripts/build_video.py

Reads the frames captured from the running application (see ``record_demo.py``, or a
Playwright MCP session driving the same flow), renders title cards and burns in a
caption per frame, then crossfades the lot into ``demo/warba-client-documentation.mp4``.

Nothing here is a mockup. Every screenshot is the real application talking to the real
database and the real model; this script only sequences them and adds words.

Requires ffmpeg on PATH and Pillow.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
STILLS = ROOT / "demo" / "stills"
BUILD = ROOT / "demo" / "build"
OUT = ROOT / "demo" / "warba-client-documentation.mp4"

W, H = 1280, 720
FPS = 30
XFADE = 0.5  # seconds of crossfade between every pair of segments

BRAND = (0, 88, 74)  # Warba green
BRAND_DEEP = (0, 58, 49)
GOLD = (201, 162, 39)
PAPER = (247, 249, 250)
INK = (16, 22, 28)
# A solid tint rather than white-with-alpha: these are pasted onto RGB images, where
# an alpha channel is silently dropped and the text comes out fully white.
MUTED = (176, 205, 198)

FONT_DIR = Path("C:/Windows/Fonts")


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a system font, falling back to whatever Pillow can find.

    Segoe UI is the closest system face to the Inter used in the app, so the cards and
    the screenshots do not look like they came from two different products.
    """
    for candidate in (FONT_DIR / name, Path(name)):
        try:
            return ImageFont.truetype(str(candidate), size)
        except OSError:
            continue
    return ImageFont.load_default(size)


BOLD = lambda s: _font("segoeuib.ttf", s)  # noqa: E731
SEMI = lambda s: _font("seguisb.ttf", s)  # noqa: E731
BODY = lambda s: _font("segoeui.ttf", s)  # noqa: E731
LIGHT = lambda s: _font("segoeuil.ttf", s)  # noqa: E731
MONO = lambda s: _font("consola.ttf", s)  # noqa: E731


# --------------------------------------------------------------------------- text


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words, line = paragraph.split(" "), ""
        for word in words:
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=font) <= max_width:
                line = trial
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
    return lines


def _block(draw, lines, font, x, y, fill, leading) -> int:
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += leading
    return y


# --------------------------------------------------------------------------- cards


def title_card(path: Path, kicker: str, headline: str, body: str = "") -> None:
    """A full-bleed brand card. Used to carry the argument between screenshots."""
    img = Image.new("RGB", (W, H), BRAND_DEEP)
    draw = ImageDraw.Draw(img)

    # A soft diagonal wash so the card is not a flat rectangle of green.
    for i in range(H):
        t = i / H
        draw.line(
            [(0, i), (W, i)],
            fill=(
                int(BRAND_DEEP[0] + (BRAND[0] - BRAND_DEEP[0]) * t),
                int(BRAND_DEEP[1] + (BRAND[1] - BRAND_DEEP[1]) * t),
                int(BRAND_DEEP[2] + (BRAND[2] - BRAND_DEEP[2]) * t),
            ),
        )

    draw.rectangle([0, 0, 8, H], fill=GOLD)

    x, max_w = 104, W - 260
    head_font = BOLD(58) if len(headline) < 60 else BOLD(46)
    head_leading = int(head_font.size * 1.24)
    body_font = LIGHT(27)

    head_lines = wrap(draw, headline, head_font, max_w)
    body_lines = wrap(draw, body, body_font, max_w) if body else []

    # Measure first, then centre. Cards carry between one and four lines of body copy, and
    # a fixed top margin leaves the short ones stranded against the top edge.
    block_h = (
        (52 if kicker else 0)
        + len(head_lines) * head_leading
        + (26 + len(body_lines) * 42 if body_lines else 0)
    )
    y = max(96, (H - block_h) // 2)

    if kicker:
        draw.text((x, y), kicker.upper(), font=SEMI(21), fill=GOLD)
        y += 52

    y = _block(draw, head_lines, head_font, x, y, (255, 255, 255), head_leading)

    if body_lines:
        y += 26
        _block(draw, body_lines, body_font, x, y, MUTED, 42)

    img.save(path)


def captioned(src: Path, dst: Path, caption: str, note: str = "") -> None:
    """Overlay a caption bar on a screenshot.

    The bar sits at the bottom and is opaque enough to read against any part of the UI
    that happens to be behind it — a translucent strip over a white table is unreadable
    on a phone, which is where most of this will be watched.
    """
    shot = Image.open(src).convert("RGB")
    if shot.size != (W, H):
        shot = shot.resize((W, H), Image.LANCZOS)

    img = Image.new("RGB", (W, H))
    img.paste(shot, (0, 0))

    scratch = ImageDraw.Draw(img)
    cap_font, note_font = SEMI(29), BODY(21)
    cap_lines = wrap(scratch, caption, cap_font, W - 128)
    note_lines = wrap(scratch, note, note_font, W - 128) if note else []

    bar_h = 60 + len(cap_lines) * 38 + (len(note_lines) * 30 + 10 if note_lines else 0)
    bar_top = H - bar_h

    draw = ImageDraw.Draw(img)
    # Fully opaque. A translucent bar lets the UI behind it show through the letterforms,
    # which is unreadable at phone size — where most of this will actually be watched.
    draw.rectangle([0, bar_top, W, H], fill=BRAND_DEEP)
    draw.rectangle([0, bar_top, W, bar_top + 3], fill=GOLD)

    y = bar_top + 26
    y = _block(draw, cap_lines, cap_font, 64, y, (255, 255, 255), 38)
    if note_lines:
        y += 10
        _block(draw, note_lines, note_font, 64, y, MUTED, 30)

    img.save(dst)


# --------------------------------------------------------------------------- script

# (source frame or None for a card, seconds, caption/headline, note/body, kicker)
STORYBOARD: list[tuple[str | None, float, str, str, str]] = [
    (None, 4.0, "AI-Powered Client Documentation",
     "A working system that drafts corporate banking documents from an RM's raw meeting "
     "notes — and refuses to write anything it cannot prove.",
     "Warba Bank · Corporate Banking AI Challenge · Track 1"),

    (None, 4.6, "The risk was never slow writing.",
     "A Relationship Manager can write a call report in an hour. What a bank cannot "
     "accept is a fluent, confident, wrong number sitting inside it — or a conventional "
     "interest product described as if it were Islamic.",
     "The problem"),

    ("01-login.png", 2.8, "Sign in as a Relationship Manager",
     "Every action is attributable to a named person.", ""),

    ("02-portfolio.png", 3.2, "You see only the clients you own",
     "Portfolio scoping is enforced server-side, not hidden in the UI.", ""),

    ("03-generate.png", 4.4, "Paste the raw meeting notes — that is the entire input",
     "Bullet points, half sentences, exactly as they were jotted down between meetings.", ""),

    ("04-generating.png", 3.0, "Two passes, not one",
     "Pass 1 extracts claims and verifies each against the source. Pass 2 writes the "
     "document from that ledger and never sees the raw sources.", ""),

    ("05-review.png", 3.6, "A complete draft, in about 25 seconds",
     "Eight sections, structured the way the bank's template expects.", ""),

    ("06-gap-marker.png", 5.6, "Every sentence carries the sources it came from",
     "And what the notes did not say is marked MISSING — in amber, in the document, "
     "rather than quietly invented.", ""),

    (None, 4.8, "If the model cannot quote it, the system deletes it.",
     "The model supplies a verbatim quote; our own code searches the real source text "
     "for it. No fuzzy matching — a single altered digit fails. Unsupported claims never "
     "reach the page.",
     "How the guarantee works"),

    ("10-shariah-block.png", 5.8, "Non-compliant terminology stops the draft before it exists",
     "A deterministic word-list gate over a reviewable YAML file — auditable by "
     "compliance, not buried in a prompt. Each finding cites its rule ID.", ""),

    ("07-approval-blocked.png", 5.6, "Unresolved gaps block approval outright",
     "The button is disabled and every missing item is listed by name. There is no "
     "override, and no timer that approves anything on its own.", ""),

    ("08-approval-confirm.png", 4.6, "A named human accepts authorship",
     "No default-checked box, no keyboard shortcut. The exact content hash being "
     "approved is shown, so the RM approves the version they actually read.", ""),

    ("09-approved.png", 4.2, "Approved — and permanently recorded",
     "Who approved it, when, and the exact content, written to a hash-chained "
     "append-only audit trail.", ""),

    (None, 5.6, "Guarantees you can check, not claims you have to trust.",
     "Audit immutability enforced by database privilege — the app role holds INSERT and "
     "SELECT only. Synthetic-only data enforced by a CHECK constraint. Provider "
     "portability enforced by lint. 226 tests.",
     "Why it holds up"),

    (None, 4.4, "Built with spec-driven development",
     "Constitution → spec → plan → tasks → implementation, with every decision recorded. "
     "FastAPI · PostgreSQL · React · Claude and Gemini behind one port.",
     "Warba Bank Corporate Banking AI Challenge · Track 1"),
]


def build() -> int:
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found on PATH", file=sys.stderr)
        return 1

    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    frames: list[tuple[Path, float]] = []
    missing: list[str] = []

    for i, (src, seconds, headline, body, kicker) in enumerate(STORYBOARD):
        dst = BUILD / f"{i:02d}.png"
        if src is None:
            title_card(dst, kicker, headline, body)
        else:
            source = STILLS / src
            if not source.exists():
                missing.append(src)
                continue
            captioned(source, dst, headline, body)
        frames.append((dst, seconds))

    if missing:
        print(f"missing frames, skipped: {', '.join(missing)}", file=sys.stderr)
    print(f"prepared {len(frames)} segments in {BUILD}")

    # Crossfade chain. Each xfade consumes XFADE seconds of overlap, so every offset is
    # the running total minus the fades already spent.
    cmd: list[str] = ["ffmpeg", "-y"]
    for path, seconds in frames:
        cmd += ["-loop", "1", "-t", f"{seconds:.2f}", "-i", str(path)]

    filters: list[str] = []
    for i in range(len(frames)):
        filters.append(
            f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0F1618,setsar=1,fps={FPS}[c{i}]"
        )

    last, elapsed = "c0", frames[0][1]
    for i in range(1, len(frames)):
        offset = elapsed - XFADE
        label = f"x{i}"
        filters.append(
            f"[{last}][c{i}]xfade=transition=fade:duration={XFADE}:offset={offset:.2f}[{label}]"
        )
        last = label
        elapsed += frames[i][1] - XFADE

    filters.append(f"[{last}]format=yuv420p[v]")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[v]",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-movflags", "+faststart",
        str(OUT),
    ]

    print(f"rendering {elapsed:.1f}s …")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-3000:], file=sys.stderr)
        return result.returncode

    print(f"\n{OUT}  ({OUT.stat().st_size // 1024} KB, {elapsed:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
