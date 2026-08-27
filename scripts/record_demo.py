"""Record a demonstration video of the running application.

Drives the real app against the real database and the real model — nothing is mocked,
staged, or sped up. What the video shows is what the system does.

    python scripts/record_demo.py

Requires the stack to be up:

    docker compose up -d
    cd backend && uvicorn app.main:app --port 8000
    cd frontend && npm run dev

Output: ``demo/raw/*.webm`` plus stills in ``demo/stills/``. Run ``scripts/build_video.py``
afterwards to add title cards and produce an MP4.

Pacing is deliberate. The three moments that carry the whole argument each get time to
be read rather than glimpsed:

  · the gap markers  — the system saying "I could not source this"
  · approval blocked — the system refusing to let an unresolved gap through
  · the approval dialog — a named human taking responsibility
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

APP = "http://localhost:5173"
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "demo" / "raw"
STILLS = ROOT / "demo" / "stills"

WIDTH, HEIGHT = 1280, 720

# Deliberately messy, exactly as an RM would jot it down between meetings. The point
# of the demo is that this is the *entire* input.
NOTES = """Client: Al-Sabah Trading Company W.L.L. (Synthetic) / WB-CORP-1001
Date: 14 August 2026
Present: RM (Warba), Finance Director, Managing Director
Channel: In person, client premises Shuwaikh

- MD said summer season stronger than last year
- Current Murabaha limit KWD 1,200,000, utilisation now around KWD 840,000
- Asked whether limit could be reviewed upward, indicative ask KWD 1,800,000
- FD confirmed FY2025 audited turnover KWD 4,500,000, net profit KWD 385,000
- Warehouse equipment under existing Ijara performing fine
- Concern: receivable from one large distributor around 90 days overdue, not provisioned
- Client wants to discuss trade finance for a new import line from Turkey
- Action: RM to send facility review checklist
- Action: FD to provide updated cash flow forecast"""


def beat(seconds: float) -> None:
    """A pause long enough for a viewer to actually read what is on screen."""
    time.sleep(seconds)


def shot(page: Page, name: str) -> None:
    STILLS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(STILLS / f"{name}.png"))


def glide(page: Page, to: int, ms: int = 900) -> None:
    """Smooth-scroll to a position.

    Native smooth scrolling rather than a jump: an abrupt cut mid-document reads as a
    glitch on video, and the reader loses their place in the section they were on.
    """
    page.evaluate(f"window.scrollTo({{ top: {to}, behavior: 'smooth' }})")
    time.sleep(ms / 1000)


def record() -> int:
    RAW.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            record_video_dir=str(RAW),
            record_video_size={"width": WIDTH, "height": HEIGHT},
            device_scale_factor=1,
        )
        page = context.new_page()

        # ---- 1. Sign in -------------------------------------------------
        page.goto(APP, wait_until="networkidle")
        beat(1.4)
        shot(page, "01-login")

        page.fill('input[type="password"]', "Demo!2026")
        beat(0.7)
        page.click('button[type="submit"]')
        page.wait_for_selector(".portfolio__list button", timeout=20_000)
        beat(1.8)
        shot(page, "02-portfolio")

        # ---- 2. Pick a client -------------------------------------------
        page.click('button:has-text("Al-Sabah Trading Company")')
        page.wait_for_selector("textarea", timeout=10_000)
        beat(1.2)

        # ---- 3. Paste the notes -----------------------------------------
        # Typed rather than filled, so the video shows real notes going in rather than
        # text materialising. Fast enough not to bore, slow enough to read.
        page.click("textarea")
        page.type("textarea", NOTES, delay=4)
        beat(1.5)
        shot(page, "03-notes")

        glide(page, 700)
        beat(1.6)
        shot(page, "04-sources")

        # ---- 4. Generate -------------------------------------------------
        page.click('button:has-text("Generate call report")')
        beat(2.5)
        shot(page, "05-generating")

        page.wait_for_selector(".section", timeout=180_000)
        beat(2.2)
        glide(page, 0)
        beat(1.5)
        shot(page, "06-review-top")

        # ---- 5. Read the document, gaps included -------------------------
        height = page.evaluate("document.body.scrollHeight")
        for fraction in (0.18, 0.34, 0.50, 0.66, 0.82):
            glide(page, int(height * fraction))
            beat(1.9)
        shot(page, "07-gaps")

        # ---- 6. Approval is blocked --------------------------------------
        glide(page, height)
        beat(1.2)
        page.click('button:has-text("Approve")')
        beat(2.6)
        shot(page, "08-approval-dialog")

        page.screenshot(path=str(STILLS / "08b-approval-blocked.png"))
        beat(1.4)

        page.click('button:has-text("Cancel")')
        beat(1.0)

        # ---- 7. Resolve the gaps, then approve ---------------------------
        # Each gap is acknowledged explicitly, which is the point: the RM decides, and
        # the acknowledgement is recorded against their name.
        resolved = 0
        for _ in range(12):
            buttons = page.locator('.gap--open button:has-text("Resolve")')
            if buttons.count() == 0:
                break
            page.once("dialog", lambda d: d.accept("Not recorded in the meeting notes."))
            buttons.first.click()
            page.wait_for_timeout(1200)
            resolved += 1
        print(f"  gaps acknowledged: {resolved}")
        beat(1.4)
        shot(page, "09-gaps-resolved")

        glide(page, page.evaluate("document.body.scrollHeight"))
        beat(1.0)
        page.click('button:has-text("Approve")')
        beat(1.8)

        checkbox = page.locator(".dialog__confirm input[type=checkbox]")
        if checkbox.count():
            checkbox.check()
            beat(1.5)
            shot(page, "10-approval-confirm")
            page.click('button:has-text("Approve document")')
            page.wait_for_selector(".approved", timeout=30_000)
            beat(2.6)
            shot(page, "11-approved")
        else:
            print("  ! approval dialog still blocked — capturing state")
            shot(page, "10-still-blocked")

        beat(1.5)
        context.close()
        browser.close()

    videos = sorted(RAW.glob("*.webm"))
    if not videos:
        print("no video produced", file=sys.stderr)
        return 1

    print(f"\nrecorded: {videos[-1]}  ({videos[-1].stat().st_size // 1024} KB)")
    print(f"stills:   {len(list(STILLS.glob('*.png')))} frames in {STILLS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(record())
