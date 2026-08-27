---
id: 0005
title: LinkedIn Demo Video And UI Fixes
stage: misc
date: 2026-08-27
surface: agent
model: claude-opus-5
feature: 001-ai-client-documentation
branch: main
user: Muhammad Yaseen
command: (freeform request)
labels: ["demo", "video", "ui-bug", "shariah-screening", "playwright", "linkedin"]
links:
  spec: specs/001-ai-client-documentation/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - frontend/src/components/ApprovalDialog.tsx
 - frontend/src/api/client.ts
 - frontend/src/styles.css
 - frontend/index.html
 - scripts/build_video.py
 - scripts/record_demo.py
 - demo/LINKEDIN.md
 - demo/warba-client-documentation.mp4
 - demo/stills/*.png
 - .gitignore
tests:
 - backend pytest suite — 226 passed, 6 skipped
 - frontend tsc --noEmit — clean
 - frontend vite build — clean
 - manual E2E via Playwright MCP against live stack (Postgres 5434, Gemini
   gemini-flash-lite-latest): generate → gap markers → approval blocked → resolve
   → approve; and a separate Shariah-block run returning 451
---

## Prompt

achaa ab bat sunoo merii playwrite connected haii mujayy ya project linkedin par past
karna haiii to videoo bana kar doo full videoo mayy poora sab dikhoo real hota huaaa ya
project kis lia haii kia karta haiii sab kuch jaldiee karoooo

(followed by, after an interrupted standalone recording script: "playwrite connected
haiii" — redirecting to the Playwright MCP rather than `scripts/record_demo.py`.)

## Response snapshot

Drove the real application end-to-end through the Playwright MCP at 1280×720 and captured
eleven stills, then assembled a 59-second captioned MP4.

Two genuine defects surfaced while recording — both invisible to the test suite, both on
paths a user hits immediately:

1. **Approval dialog mis-positioned.** `main` carried `animation: rise … both`. The `both`
   fill mode retains the animation's end transform permanently, and any transform on an
   ancestor becomes the containing block for `position: fixed`. The backdrop was therefore
   sized against a 2991px-tall `<main>` instead of the 720px viewport, so on a long
   document the dialog rendered far below the fold. Fixed at both ends: `ApprovalDialog`
   now renders through `createPortal` into `<body>` (immune to ancestor transforms), and
   `main` uses `backwards` fill so it leaves no transform behind. Note the portal needs
   `globalThis.document.body` — the component's `document` prop shadows the global.

2. **Shariah block reported itself as a generic failure.** The API client did
   `body?.detail ?? body`, intended to unwrap FastAPI's `HTTPException` envelope. But our
   own handlers return the error flat and use `detail` to carry the payload, so the unwrap
   discarded `code` and `message` and substituted the findings object — producing "The
   request could not be completed." The gate worked; it just would not say why. Now
   unwraps only the nested shape, keyed on `code` being present inside `detail`. The RM
   sees all five prohibited terms with rule IDs (SH-012, SH-002b, SH-001, SH-002c,
   SH-002a).

The second was the more serious: deterministic Shariah screening is one of the strongest
controls in the system, and it was presenting as an unexplained error.

`scripts/build_video.py` renders brand title cards, burns a caption bar into each still,
and crossfades the sequence with ffmpeg. Caption bars are fully opaque — a translucent
strip over the white document UI is unreadable at phone size.

## Outcome

- ✅ Impact: A 59s demo video (1280×720, 2.9 MB) suitable for LinkedIn, plus post copy in
  two lengths. Two user-facing UI defects fixed. Pushed as `e081d3d`.
- 🧪 Tests: 226 passed, 6 skipped. Frontend typechecks and builds. Full E2E re-verified
  live against Postgres and Gemini, including the 451 screening path.
- 📁 Files: 4 frontend files modified; `scripts/build_video.py`, `demo/LINKEDIN.md`, the
  video and 11 stills added; `.gitignore` extended for Playwright MCP scratch and
  intermediate frames.
- 🔁 Next prompts: write the team background section in `SUBMISSION.md` §1 (only the user
  can); make the GitHub repository public before submitting; re-run the live Gemini
  evaluation when the free-tier quota resets to record a 5/5 `BASELINE.md`.
- 🧠 Reflection: Driving the real UI found two bugs that 226 unit, integration and contract
  tests did not. Both were presentation-layer failures on the happy path — precisely the
  class of defect that automated backend testing is structurally blind to.

## Evaluation notes (flywheel)

- Failure modes observed: (a) CSS `animation-fill-mode: both` silently creating a
  containing block for fixed-position descendants; (b) an over-eager error-envelope unwrap
  swallowing a compliance control's explanation.
- Graders run and results (PASS/FAIL): backend pytest PASS (226/226); frontend typecheck
  PASS; frontend build PASS; manual E2E PASS; Shariah 451 path PASS with full findings.
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): add a frontend test layer — there is currently
  none (`frontend/tests/` is empty), and both defects here were frontend-only.
