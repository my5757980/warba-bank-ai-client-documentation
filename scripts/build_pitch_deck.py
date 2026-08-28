"""Render SUBMISSION.md into the single PDF the challenge portal accepts.

    python scripts/build_pitch_deck.py

The Ignyte portal takes exactly one file — "Pitch Deck", max 15 MB, one of
`.pdf/.pptx/.docx/.txt`. So everything a judge needs has to live in this one document,
including the links to the repository and the demo video, which cannot be uploaded
alongside it.

`SUBMISSION.md` stays the single source of truth; this script only typesets it. Images
referenced from the markdown are inlined as data URIs so the PDF is self-contained.

Chromium does the rendering (via Playwright) rather than WeasyPrint: WeasyPrint needs GTK
libraries that are awkward on Windows, and Chromium's print engine handles the tables and
page breaks here without special-casing.
"""

from __future__ import annotations

import base64
import mimetypes
import re
import sys
from pathlib import Path

from markdown_it import MarkdownIt
from playwright.sync_api import sync_playwright
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "SUBMISSION.md"
OUT = ROOT / "demo" / "Warba-Track1-Muhammad-Yaseen.pdf"

REPO = "https://github.com/my5757980/warba-bank-ai-client-documentation"
VIDEO_NOTE = "demo/warba-client-documentation.mp4 in the repository"

MAX_BYTES = 15 * 1024 * 1024  # the portal's hard limit


def inline_images(html: str) -> str:
    """Replace relative <img src> with data URIs so the PDF carries its own images."""

    def repl(match: re.Match[str]) -> str:
        src = match.group(1)
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)

        path = (ROOT / src.lstrip("./")).resolve()
        if not path.exists():
            print(f"  ! image not found, dropped: {src}", file=sys.stderr)
            return ""

        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
        return match.group(0).replace(src, f"data:{mime};base64,{payload}")

    return re.sub(r'<img[^>]*\bsrc="([^"]+)"', repl, html)


def strip_local_links(html: str) -> str:
    """Turn repository-relative links into plain text.

    A link to `./backend/` is live and useful on GitHub and dead in a PDF. Judges reading
    the PDF should see the path as a path, not as a blue word that does nothing.
    """

    def repl(match: re.Match[str]) -> str:
        href, text = match.group(1), match.group(2)
        if href.startswith(("http://", "https://", "#", "mailto:")):
            return match.group(0)
        return f'<span class="path">{text}</span>'

    return re.sub(r'<a href="([^"]+)"[^>]*>(.*?)</a>', repl, html, flags=re.DOTALL)


COVER = f"""
<section class="cover">
  <div class="cover__rule"></div>
  <p class="cover__kicker">Warba Bank · Corporate Banking AI Challenge</p>
  <h1 class="cover__title">AI-Powered Client Documentation</h1>
  <p class="cover__track">Track 1 — Submission</p>
  <p class="cover__lede">
    A working system that drafts corporate banking documents from a Relationship
    Manager's raw meeting notes — and refuses to write anything it cannot prove.
  </p>
  <dl class="cover__meta">
    <dt>Submitted by</dt><dd>Muhammad Yaseen — AI Engineer, K Com Solution</dd>
    <dt>Repository</dt><dd><a href="{REPO}">{REPO}</a></dd>
    <dt>Demo video</dt><dd>60-second walkthrough — {VIDEO_NOTE}</dd>
    <dt>Live app</dt><dd><a href="https://warba-bank-ai-client-documentation.vercel.app">warba-bank-ai-client-documentation.vercel.app</a><br/>
      Sign in: <strong>sara.rm@warba.demo</strong> / <strong>Demo!2026</strong> — nothing to install.</dd>
    <dt>Status</dt><dd>Deployed and running on synthetic data · 257 tests · 28 live end-to-end checks pass</dd>
  </dl>
</section>
"""

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm; }
@page :first { margin: 0; }

* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 10.2pt; line-height: 1.58; color: #10161c; margin: 0;
}

/* ------------------------------------------------------------------ cover */
.cover {
  height: 297mm; padding: 46mm 24mm 24mm; background: #003a31; color: #fff;
  position: relative; display: flex; flex-direction: column;
}
.cover__rule { position: absolute; left: 0; top: 0; bottom: 0; width: 10mm; background: #c9a227; }
.cover__kicker { color: #c9a227; font-size: 10.5pt; letter-spacing: .13em;
  text-transform: uppercase; font-weight: 600; margin: 0 0 10mm; }
/* Explicit white. The shared `h1,h2,h3,h4` rule below paints headings dark green, which
   on this dark green cover renders the title invisible. */
.cover__title { color: #fff; font-size: 30pt; line-height: 1.14; font-weight: 700;
  margin: 0 0 4mm; letter-spacing: -.01em; }
.cover__track { font-size: 13pt; color: #c9a227; font-weight: 600; margin: 0 0 12mm; }
.cover__lede { font-size: 13pt; line-height: 1.55; color: #cfe0db; max-width: 135mm; margin: 0; font-weight: 300; }
.cover__meta { margin: auto 0 0; display: grid; grid-template-columns: 34mm 1fr;
  gap: 3.4mm 6mm; font-size: 9.6pt; border-top: 1px solid rgba(255,255,255,.22); padding-top: 8mm; }
.cover__meta dt { color: #9dbdb4; font-weight: 600; }
.cover__meta dd { margin: 0; color: #fff; word-break: break-word; }
.cover__meta a { color: #fff; text-decoration: none; border-bottom: 1px solid rgba(255,255,255,.35); }
/* The shared `strong` rule paints near-black, which is invisible on this dark cover —
   and the sign-in credentials are the one thing a reviewer must be able to read. */
.cover__meta strong { color: #f0c94a; font-weight: 650; }

.page-break { break-after: page; }

/* --------------------------------------------------------------- headings */
h1, h2, h3, h4 { color: #003a31; line-height: 1.25; break-after: avoid; margin: 0 0 3mm; }
h1 { font-size: 19pt; }
h2 {
  font-size: 15pt; margin-top: 11mm; padding-top: 3.5mm;
  border-top: 2.5px solid #c9a227; break-before: page;
}
h2:first-of-type { break-before: avoid; }
h3 { font-size: 12pt; margin-top: 7mm; color: #00584a; }
h4 { font-size: 10.5pt; margin-top: 5mm; color: #00584a; }
p { margin: 0 0 3.2mm; }

/* Never leave a heading, image, or table row stranded at a page foot. */
p, li, tr, img, blockquote { break-inside: avoid; }

a { color: #00584a; }
strong { font-weight: 650; color: #0a1418; }

ul, ol { margin: 0 0 3.4mm; padding-left: 5.5mm; }
li { margin-bottom: 1.4mm; }

/* ----------------------------------------------------------------- tables */
table { width: 100%; border-collapse: collapse; margin: 4mm 0 5mm; font-size: 9.2pt; break-inside: auto; }
th, td { text-align: left; padding: 2.2mm 3mm; border-bottom: 1px solid #dfe6e4; vertical-align: top; }
th { background: #eef4f2; color: #003a31; font-weight: 650; border-bottom: 1.5px solid #c9a227; }
tr:nth-child(even) td { background: #fafbfb; }

/* ------------------------------------------------------------------- code */
code {
  font-family: Consolas, "Cascadia Mono", monospace; font-size: 8.6pt;
  background: #eef4f2; color: #00463b; padding: .4mm 1.1mm; border-radius: 2px;
}
pre {
  background: #0f1a1d; color: #e6efec; padding: 3.5mm 4mm; border-radius: 3px;
  overflow-x: hidden; font-size: 8.2pt; line-height: 1.5; break-inside: avoid; margin: 3mm 0 4mm;
}
pre code { background: none; color: inherit; padding: 0; font-size: inherit; white-space: pre-wrap; word-break: break-word; }
.path { font-family: Consolas, monospace; font-size: 8.8pt; color: #00584a; }

/* ----------------------------------------------------------------- images */
img { max-width: 100%; height: auto; display: block; margin: 4mm auto 2mm;
  border: 1px solid #dfe6e4; border-radius: 3px; }

blockquote {
  margin: 4mm 0; padding: 2.5mm 4mm; border-left: 3px solid #c9a227;
  background: #fdf9ef; color: #4a4335; font-size: 9.6pt;
}
blockquote p:last-child { margin-bottom: 0; }

hr { border: none; border-top: 1px solid #e3e9e7; margin: 6mm 0; }
"""


def build() -> int:
    if not SOURCE.exists():
        print(f"missing {SOURCE}", file=sys.stderr)
        return 1

    md = MarkdownIt("commonmark", {"html": True}).enable("table").enable("strikethrough")
    text = SOURCE.read_text(encoding="utf-8")

    # The cover repeats the title block, so drop the markdown one rather than print it twice.
    body = re.sub(r"\A#\s.*?\n---\n", "", text, count=1, flags=re.DOTALL)

    html = md.render(body)
    html = inline_images(html)
    html = strip_local_links(html)

    def wrap(inner: str) -> str:
        return (
            f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>{CSS}</style></head><body>{inner}</body></html>"
        )

    scratch_dir = ROOT / "demo" / "build"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    cover_html = scratch_dir / "cover.html"
    body_html = scratch_dir / "body.html"
    cover_html.write_text(wrap(COVER), encoding="utf-8")
    body_html.write_text(wrap(html), encoding="utf-8")

    footer = (
        "<div style='width:100%;font-size:7.5pt;color:#8a9997;"
        "font-family:Segoe UI,sans-serif;padding:0 16mm;display:flex;"
        "justify-content:space-between;'>"
        "<span>Warba Bank Corporate Banking AI Challenge · Track 1 · Muhammad Yaseen</span>"
        "<span class='pageNumber'></span></div>"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cover_pdf = scratch_dir / "_cover.pdf"
    body_pdf = scratch_dir / "_body.pdf"

    # Rendered as two documents and merged. Chromium applies header/footer to every page or
    # to none, and a page number stamped across the full-bleed cover looks like a mistake.
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()

        page.goto(cover_html.as_uri(), wait_until="networkidle")
        page.pdf(path=str(cover_pdf), format="A4", print_background=True,
                 margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})

        page.goto(body_html.as_uri(), wait_until="networkidle")
        page.pdf(
            path=str(body_pdf),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=footer,
            margin={"top": "18mm", "bottom": "20mm", "left": "16mm", "right": "16mm"},
        )
        browser.close()

    merged = PdfWriter()
    for part in (cover_pdf, body_pdf):
        merged.append(str(part))
    with OUT.open("wb") as fh:
        merged.write(fh)
    merged.close()

    size = OUT.stat().st_size
    print(f"{OUT}  ({size / 1024 / 1024:.2f} MB)")

    if size > MAX_BYTES:
        print(
            f"! over the portal's 15 MB limit by {(size - MAX_BYTES) / 1024 / 1024:.2f} MB",
            file=sys.stderr,
        )
        return 1

    print(f"within the 15 MB portal limit ({MAX_BYTES / 1024 / 1024:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
