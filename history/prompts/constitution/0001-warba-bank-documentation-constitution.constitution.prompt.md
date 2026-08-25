---
id: 0001
title: Warba Bank Documentation Constitution
stage: constitution
date: 2026-08-21
surface: agent
model: claude-opus-5
feature: none
branch: none (not a git repository)
user: ms5373268@gmail.com
command: /sp.constitution
labels: ["constitution", "banking", "shariah-compliance", "security", "human-in-the-loop", "auditability"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
 - .specify/memory/constitution.md (created — v1.0.0, replaced template)
 - history/prompts/constitution/0001-warba-bank-documentation-constitution.constitution.prompt.md (created)
tests:
 - Placeholder validation: grep for `[ALL_CAPS]` and `{{TOKEN}}` patterns — PASS (no matches)
 - Date format check: ISO YYYY-MM-DD in Version line — PASS
 - Version/report coherence: Sync Impact Report states 1.0.0, footer states 1.0.0 — PASS
---

## Prompt

You are helping me build a production-ready solution for Warba Bank's Corporate Banking AI Challenge – Track 1: AI-Powered Client Documentation.

We are following Spec-Driven Development.

First step: Create the Constitution (non-negotiable principles).

Write a clear and strict Constitution for this project. It must include:

- Banking-grade security & compliance requirements
- Shariah-governance readiness
- Human-in-the-loop principle (RM always has final approval)
- Accuracy over speed (minimize hallucinations)
- Simple and fast user experience for Relationship Managers
- Modular and scalable architecture
- No real client data in the prototype (only anonymised/dummy data)
- Auditability of every generated document

Make the Constitution short, clear, and strong. Write it in professional English.

## Response snapshot

Ratified `.specify/memory/constitution.md` at **v1.0.0**, replacing the unfilled SpecKit
template. The user requested eight principles; the template carried six placeholder slots,
so two additional principle sections were added and the numbering extended to VIII.

Eight core principles, each with binding MUST/MUST NOT rules plus a one-line rationale:

- **I. Banking-Grade Security & Compliance (NON-NEGOTIABLE)** — TLS 1.2+ / at-rest
  encryption, RBAC scoped to the RM's own portfolio, no hardcoded secrets (build-blocking),
  approved-third-parties-only, CBK / AML / KYC / data-residency alignment.
- **II. Shariah-Governance Readiness (NON-NEGOTIABLE)** — Islamic finance structures
  (Murabaha, Ijara, Wakala), no riba or conventional-loan language, mandatory
  `PENDING_REVIEW` Shariah status field, terminology from a reviewable vocabulary source
  rather than model invention, flag-don't-guess on unmapped products.
- **III. Human-in-the-Loop: The RM Decides (NON-NEGOTIABLE)** — nothing is finalised
  without explicit RM approval; approval is a deliberate recorded event, never a default or
  timeout; drafts are editable and labelled AI-generated; prior versions preserved.
- **IV. Accuracy Over Speed** — every factual claim traceable to a supplied source,
  unsourced generation prohibited, missing data rendered as explicit `[MISSING: ...]`
  markers instead of plausible text, per-section citations, low-confidence flagging,
  accuracy regressions block release.
- **V. Simple, Fast Experience for RMs** — core journey in ≤5 interactions, <3s perceived
  latency for interactive actions, streaming progress for long generation, plain banking
  language, remove any feature adding cognitive load without measured benefit.
- **VI. Modular & Scalable Architecture** — separated, independently testable layers; LLM
  behind a swap-friendly abstraction; new document types via configuration and templates
  without touching the generation engine; prompts/templates/vocabularies versioned in-repo.
- **VII. No Real Client Data (NON-NEGOTIABLE)** — synthetic/anonymised fixtures only; no
  real identifiers in repo, environments, logs, or demos; purge-and-disclose on accidental
  introduction; automated identifier scanning.
- **VIII. Total Auditability** — per-generation event record (timestamp, RM ID, client ref,
  doc type, input sources, model + version, prompt/template version, output hash); immutable
  append-only trail not user-editable; version retention linking approvals to exact inputs;
  machine-readable export for compliance.

Supporting sections added:

- **Security, Compliance & Data Constraints** — Confidential-by-default classification,
  structured logs carrying identifiers not payloads, append-only retention of approval
  records, third-party data-handling disclosure in the plan, **fail-closed** posture on any
  validation/retrieval/model failure, and uploaded document content treated as untrusted
  data (prompt-injection defence), never as instructions.
- **Development Workflow & Quality Gates** — SDD flow, mandatory eight-principle
  Constitution Check in every `plan.md`, smallest viable diff, grounding/hallucination tests,
  PHR + ADR traceability, and a concrete Definition of Done.
- **Governance** — NON-NEGOTIABLE principles (I, II, III, VII) as hard merge blockers;
  amendment procedure requiring rationale + version bump + Sync Impact Report update +
  template consistency review; semantic versioning policy; PR/plan compliance review;
  `CLAUDE.md` explicitly subordinate to the constitution.

A Sync Impact Report is prepended as an HTML comment recording the
TEMPLATE → 1.0.0 transition, the placeholder → principle mapping, and template
propagation status. Existing templates (`plan-template.md`, `spec-template.md`,
`tasks-template.md`, `.claude/commands/*.md`) were reviewed and found structurally
compatible — the plan template's "Constitution Check" gate is constitution-driven by
design, so no template edits were required.

## Outcome

- ✅ Impact: Project now has ratified, enforceable non-negotiable principles. All future
  `/sp.specify`, `/sp.plan`, and `/sp.tasks` output is gated against these eight principles.
- 🧪 Tests: Placeholder scan PASS (no `[ALL_CAPS]` or `{{TOKEN}}` residue); ISO date format
  PASS; version coherence between Sync Impact Report and footer PASS.
- 📁 Files: 1 constitution created (v1.0.0), 1 PHR created. No template edits needed.
- 🔁 Next prompts: `/sp.specify` for the Track 1 client-documentation feature; optionally
  `/sp.adr` once the LLM provider, retrieval strategy, and audit-store decisions are made.
- 🧠 Reflection: The user's eight requirements mapped cleanly onto principles, but two
  cross-cutting risks (fail-closed behaviour and prompt injection from uploaded client
  documents) did not fit any single principle and were placed in the Security section so
  they remain enforceable rather than implicit.

## Evaluation notes (flywheel)

- Failure modes observed: The template shipped with six principle slots against eight stated
  requirements; a naive fill would have merged or dropped requirements. Slots were extended
  instead. A heredoc write failed on the shell first attempt and was completed with native
  file tools.
- Graders run and results (PASS/FAIL): Placeholder-residue grader PASS; date-format grader
  PASS; version-coherence grader PASS; principle-coverage grader (8 user requirements → 8
  principles) PASS.
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): During `/sp.plan`, assert that the Constitution
  Check table lists all eight principles by name — an omitted principle is the most likely
  silent gate failure.
