---
id: 0004
title: AI Client Documentation Task Breakdown
stage: tasks
date: 2026-08-21
surface: agent
model: claude-opus-5
feature: 001-ai-client-documentation
branch: 001-ai-client-documentation (directory only — repository is not git-initialised)
user: ms5373268@gmail.com
command: /sp.tasks
labels: ["tasks", "sequencing", "evaluation-gate", "anti-hallucination", "risk-ordering", "mvp"]
links:
  spec: specs/001-ai-client-documentation/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - specs/001-ai-client-documentation/tasks.md (created — 170 tasks across 8 phases)
 - history/prompts/001-ai-client-documentation/0004-ai-client-documentation-task-breakdown.tasks.prompt.md (created)
tests:
 - Task ID sequence T001..T170, no gaps or duplicates — PASS
 - Checklist format compliance (checkbox + ID + optional [P] + [Story] + file path) — PASS (0 violations)
 - Story label placement (present in story phases, absent in setup/foundational/polish) — PASS
 - Sequencing constraint: evaluation harness (Phase 4) precedes US2 and US3 — PASS
 - Task counts verified by grep against the summary table — corrected after initial mismatch
---

## Prompt

The Implementation Plan is complete and Constitution Check has passed 8/8.

Now proceed to /sp.tasks

Break down the entire implementation into clear, ordered, and actionable tasks.

Requirements for the task list:
- Tasks should be small and executable
- Proper sequencing (dependencies clear)
- Evaluation harness / anti-hallucination tests must come before high-risk document types (especially Credit Memo)
- Group tasks by phases if needed
- Each task should have a clear outcome

Generate a complete and practical task list ready for implementation.

## Response snapshot

Ran `check-prerequisites.ps1` (all four optional design docs present), then generated
`tasks.md` — **170 tasks across 8 phases**, every one carrying a checkbox, sequential ID,
optional `[P]` marker, story label where applicable, and an exact file path.

**The sequencing decision the user asked for, and how it was implemented.** The evaluation
harness cannot be built before a working pipeline exists to measure, so it cannot simply go
first. It was placed as **Phase 4 — a hard quality gate immediately after the P1 MVP** — where
it blocks *both* US2 and US3 rather than only the credit memo. This satisfies the requirement
more strictly than asked: the fabricated-figure gate must pass before any document type beyond
the MVP is built. The rationale is stated at the top of the file so a future contributor does
not reorder it for convenience:

> Building the credit memo before the fabricated-figure gate is measurable would invert the
> risk ordering the specification deliberately established — DT3 is the output where a wrong
> number causes real harm.

**Phase structure**

| Phase | Content | Tasks |
|-------|---------|-------|
| 1 | Setup — projects, tooling, provider-boundary lint rule | 10 |
| 2 | Foundational — the deterministic guarantees, in 10 sub-groups (2A–2J) | 69 |
| 3 | US1 Call Report (P1) 🎯 MVP | 29 |
| 4 | **Evaluation Harness ⚠️ QUALITY GATE** | 14 |
| 5 | US2 Client Profile (P2) | 13 |
| 6 | US3 Credit Memo (P3) ⚠️ HIGH RISK | 13 |
| 7 | US4 Compliance Audit (P4) | 10 |
| 8 | Polish | 12 |

**Second ordering constraint applied**: deterministic guarantees are built before the features
that depend on them. Screening (2E), ledger validation (2G), the audit chain (2B), and the
approval state machine (2H) all land in Phase 2, because every user story inherits its
constitutional compliance from them. A story built before its guarantee exists would need
retrofitting — and retrofitted guarantees are the ones that end up partial.

**Tasks where a constitutional principle becomes executable code** — these were written to be
individually verifiable rather than folded into larger work items:

- **T005** — ruff banned-api rule making `import anthropic` an error outside the single adapter
  module. NFR-SCA-04 enforced mechanically, not by intent.
- **T013** — `CHECK (is_synthetic = true)` on the Client table (Principle VII).
- **T023 / T024** — the `INSERT, SELECT`-only audit grant, plus a test that asserts `UPDATE`
  and `DELETE` are refused to the application role (FR-032).
- **T047 / T049** — the two-pass split, with T049 stating explicitly that raw sources are never
  passed to the composition call. That single constraint is what makes the grounding guarantee
  hold.
- **T056** — numeric-literal tracing: every number in output must appear in a referenced claim,
  or generation fails closed. The mechanism behind SC-004.
- **T063** — the state machine as the only writer of `Document.status`.
- **T097** — the approval endpoint with all four preconditions.
- **T114** — the fabricated-figure metric, written to report a count with **no threshold**,
  because a threshold would license some fabrication.
- **T144** — a deterministic decisioning-language guard for the credit memo, so DT3's exclusion
  of ratings, recommendations, and pricing does not rest on prompt compliance.

**Phase 4 detail.** Four fixture sets (golden, known-gaps, adversarial, Shariah), five metrics,
gate enforcement, and a recorded baseline (T122). The known-gaps set is called out as mattering
as much as the golden set: a tool that invents plausible text for missing data fails silently,
and only a known-absent fixture catches it.

**Cut order under time pressure** was made explicit, because an unstated priority becomes an
ad-hoc one at 2am: polish → US3 credit memo → US4 audit UI. Never Phase 2 guarantees or Phase 4
gates. The audit *data* is written from Phase 2 regardless — only the Compliance-facing view is
deferrable.

**Validation.** IDs run T001–T170 with no gaps or duplicates; zero checklist-format violations;
story labels present in story phases and absent elsewhere. The summary table's counts were
initially wrong — I had estimated 71 parallelisable and 38 test tasks; grep showed 81 and 46.
Corrected in the file.

## Outcome

- ✅ Impact: Feature 001 has an executable, dependency-ordered task list. The
  anti-hallucination gate is structurally positioned to block the high-risk document type
  rather than trailing it.
- 🧪 Tests: ID sequence PASS; format compliance PASS (0 violations); story-label placement
  PASS; sequencing constraint PASS; counts re-derived by grep and corrected.
- 📁 Files: tasks.md (170 tasks), this PHR.
- 🔁 Next prompts: `/sp.analyze` for a cross-artifact consistency pass over spec/plan/tasks, or
  `/sp.adr` for the four flagged decisions, or `/sp.implement` to begin Phase 1.
- 🧠 Reflection: The user's requirement — harness before high-risk types — turned out to have a
  stronger form than the one requested. Gating only the credit memo would have left the client
  profile unmeasured; gating everything past the MVP costs nothing extra and makes the
  guarantee uniform. The harder judgement was Phase 2's size: 69 tasks is a large blocking
  phase, and there was a real pull toward deferring parts of it into the stories that use them.
  I kept it whole because every one of those modules carries a constitutional guarantee, and a
  guarantee retrofitted into a working feature is a guarantee with holes in it.

## Evaluation notes (flywheel)

- Failure modes observed: The summary table was written from estimates rather than measurement
  and was wrong on two counts (parallelisable tasks, test tasks) until verified by grep — a
  reminder that self-reported metrics in generated artifacts need the same verification as
  code. `check-prerequisites.ps1` again returned exit 128 from an internal git call while
  emitting valid JSON, consistent with the other scaffold scripts in this non-git repository.
- Graders run and results (PASS/FAIL): ID-sequence grader PASS; checklist-format grader PASS;
  story-label-placement grader PASS; sequencing-constraint grader PASS; count-accuracy grader
  FAIL on first pass, PASS after correction.
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): During `/sp.implement`, treat T122 (record the
  evaluation baseline) as a genuine stop-and-check rather than a checkbox — if the gates do not
  pass on the US1 pipeline, the correct response is to fix grounding before building Phase 5,
  not to note the failure and continue. That is the one point in the plan where schedule
  pressure would most plausibly defeat the design.
