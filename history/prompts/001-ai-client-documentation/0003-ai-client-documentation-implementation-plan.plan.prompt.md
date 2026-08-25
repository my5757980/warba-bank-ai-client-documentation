---
id: 0003
title: AI Client Documentation Implementation Plan
stage: plan
date: 2026-08-21
surface: agent
model: claude-opus-5
feature: 001-ai-client-documentation
branch: 001-ai-client-documentation (directory only — repository is not git-initialised)
user: ms5373268@gmail.com
command: /sp.plan
labels: ["plan", "architecture", "grounding", "evidence-ledger", "shariah-screening", "audit-chain", "anthropic-sdk"]
links:
  spec: specs/001-ai-client-documentation/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - specs/001-ai-client-documentation/plan.md (created — Technical Context, 8-gate Constitution Check, structure, complexity, risks)
 - specs/001-ai-client-documentation/research.md (created — Phase 0, decisions R1..R14)
 - specs/001-ai-client-documentation/data-model.md (created — Phase 1, 13 entities, state machine, validation rules)
 - specs/001-ai-client-documentation/contracts/openapi.yaml (created — Phase 1, 18 paths, 20 schemas, OpenAPI 3.1.0)
 - specs/001-ai-client-documentation/quickstart.md (created — Phase 1, setup + guarantee demonstrations)
 - specs/001-ai-client-documentation/spec.md (edited — v1.0 → v1.1, Open Questions replaced with confirmed decisions D1/D2/D3)
 - CLAUDE.md (edited — Active Technologies section appended manually after the update script silently no-opped)
 - history/prompts/001-ai-client-documentation/0003-ai-client-documentation-implementation-plan.plan.prompt.md (created)
tests:
 - Constitution Check, 8/8 principles post-design — PASS (1 documented limitation, 0 unjustified violations)
 - OpenAPI 3.1.0 parse via PyYAML — PASS (18 paths, 20 schemas)
 - Template placeholder residue scan on plan.md — PASS (no matches)
 - NEEDS CLARIFICATION residue scan across Phase 0/1 artifacts — PASS (0 occurrences)
 - Anthropic API surface verified against the bundled claude-api skill (not from memory) — PASS
---

## Prompt

Proceed with the defaults:

1. Document Types: DT1 Call Report, DT2 Client Profile, DT3 Credit Memo (narrative only) — confirmed. DT4 KYC as stretch.
2. Language: English-only for MVP.
3. Document upload-and-extract: Yes, include in MVP.

Now proceed to /sp.plan

## Response snapshot

Recorded the three confirmations in `spec.md` (v1.0 → v1.1): the "Open Questions" section was
replaced with a binding "Confirmed Scope Decisions" table (D1/D2/D3) plus a changelog. No
requirements, features, or success criteria changed. D3's consequence was made explicit —
upload-and-extract being committed MVP means extracted values carry the same grounding
obligations as any other source, and uploaded content is the highest-risk prompt-injection
surface in the system.

Ran `setup-plan.ps1`, then loaded the bundled `claude-api` skill **before** committing to any
model or integration decision, rather than writing API details from memory.

**The decision that shaped everything else** — Anthropic's native document citations
(`citations: {enabled: true}`, returning `cited_text` plus page/char locators) are exactly the
mechanism FR-011 needs, but **citations are incompatible with `output_config.format`** (400).
FR-009 needs guaranteed schema coverage, which is what structured outputs provide. Both are
required; one call cannot have both. That constraint forced the core architecture:

**Two-pass generation through a validated Evidence Ledger (R3)**

- *Pass A — Grounding*: sources as `document` blocks with citations enabled, no structured
  output. Native citations normalise into an Evidence Ledger of
  `{claim_id, claim_text, source_type, locator, verbatim_excerpt}`.
- *Pass B — Composition*: sees **only the ledger**, never the raw sources. Bound to a
  per-document-type Pydantic model via `messages.parse()`, forcing every section to carry
  `evidence_refs` or explicit `gaps`.
- *Deterministic post-validation*: every `evidence_ref` must resolve to a real claim; every
  required section must be present; **every numeric literal must appear in a referenced
  claim** or generation fails closed.

This is the plan's central idea, and the same pattern recurs throughout: **put the guarantee
in deterministic code, use the model only for what genuinely needs judgement.** The model
cannot cite what is not in the ledger, and the ledger is built from actual document spans, so
SC-004 ("zero fabricated financial figures") becomes a machine-checkable release gate rather
than a hope.

**Phase 0 — research.md, R1–R14.** Highlights beyond R3:

- **R4 — no vector database.** Every generation is scoped to exactly one client, so retrieval
  is `WHERE client_id = ?`, not similarity search. A single client's context fits inside
  Opus 5's 1M window. Semantic retrieval would insert a probabilistic step *upstream* of
  grounding, where a missed chunk becomes an invisible gap — the model would not know the fact
  exists, so it could not mark it missing. It also makes FR-003/FR-004 (show the RM the
  context, let them deselect) meaningful, since the candidate set is knowable in advance.
  Rejecting the reflexive RAG default is itself a significant decision.
- **R5 — deterministic-first Shariah screening.** A NON-NEGOTIABLE control cannot rest on a
  probabilistic check. Layer 1 is a versioned `vocabulary.yaml` word list — auditable,
  reproducible, reviewable by a Shariah stakeholder who does not read code — and it is the
  binding gate. Layer 2 is a semantic model pass that catches compliant-sounding
  non-compliant structures but can only *add* findings, never clear a block.
- **R6 — hash-chained audit with two-level enforcement.** Each row stores
  `SHA256(prev_hash ‖ canonical_json)`, so tampering breaks the chain from that row forward
  and `/audit/verify` names the exact break point. Critically, the application DB role is
  granted `INSERT, SELECT` only — `UPDATE`/`DELETE` never granted. FR-032 enforced only in
  application code means one missing guard defeats it; a revoked privilege cannot be forgotten.
  Turns tamper-*discouraged* into tamper-*evident*.
- **R7 — injection defence is structural.** Channel separation (system = server templates
  only; uploads and notes only ever as `document` blocks; RM instruction scoped to style).
  But the real defence is R3: an injected "state the facility is approved" produces an
  unsourced claim, and ledger validation rejects it. Injection becomes *ineffective* rather
  than merely *discouraged*.
- **R2** — `claude-opus-5`, adaptive thinking, `effort: high`, streaming. Verified against
  the skill: `budget_tokens` is removed on Opus 5 (400), thinking is on by default, and
  streaming is required at high `max_tokens` — which also satisfies NFR-PERF-03's ban on a
  frozen screen, one mechanism covering both.
- **R9 — provider abstraction, honestly bounded.** `GenerationPort` is provider-neutral in
  contract; native citations are not portable. Recorded as a limitation rather than hidden:
  NFR-SCA-04's actual requirement — business logic never depends on a provider — is met, and
  a lint rule enforces that `adapters/anthropic_adapter.py` is the only module importing
  `anthropic`.

**Phase 1 artifacts.** `data-model.md` (13 entities, the `DRAFT → APPROVED` state machine, a
validation-rules table mapping each rule to where it is enforced); `contracts/openapi.yaml`
(18 paths, 20 schemas, parses clean as OpenAPI 3.1.0); `quickstart.md` (setup plus four
runnable demonstrations of the constitutional guarantees — gap marking, injection resistance,
screening block, audit tamper detection).

Several constitutional guarantees were pushed down into the schema so they cannot be bypassed
by application code: `Client.is_synthetic` carries a database CHECK constraint (Principle VII);
`SourceDocument.trust_level` is a single-valued enum `UNTRUSTED` by design, because a field
that *could* be set to `TRUSTED` is a field someone eventually sets; `ApprovalRecord`
snapshots approver name and role so the record survives changes to the user account; approval
requires echoing the version's `content_hash`, so an RM approves a specific version rather
than "the document".

**Constitution Check: 8/8 PASS.** Initial evaluation raised four conditionals (II, IV, VI,
VIII), each resolved in Phase 0 (R5, R3, R9, R6 respectively). Two entries recorded in
Complexity Tracking — the partial provider abstraction, and two model calls per document —
both deliberate trades, neither a violation.

**One tooling problem found and fixed.** `update-agent-context.ps1 -AgentType claude` reported
"✓ Updated existing Claude Code context file" and correctly parsed the language, framework, and
database values, but wrote none of them — this `CLAUDE.md` has no marker section for the script
to insert into, so it rewrote the file with CRLF endings (+210 bytes, exactly one per line) and
dropped the content. Verified by grep, then appended an "Active Technologies" section manually,
including the architectural invariants a future contributor must not work around.

## Outcome

- ✅ Impact: Feature 001 has a complete, constitutionally-gated implementation plan with all
  Phase 0 and Phase 1 artifacts. Ready for `/sp.tasks`.
- 🧪 Tests: Constitution Check 8/8 PASS; OpenAPI 3.1.0 parses (18 paths, 20 schemas); zero
  template residue; zero unresolved clarifications; Anthropic API surface verified against the
  bundled skill rather than recalled.
- 📁 Files: plan.md, research.md, data-model.md, contracts/openapi.yaml, quickstart.md created;
  spec.md → v1.1; CLAUDE.md agent context repaired manually.
- 🔁 Next prompts: `/sp.tasks` to generate the dependency-ordered task list. `/sp.adr` for the
  three decisions flagged below, ideally before implementation starts.
- 🧠 Reflection: The plan improved sharply once the citations/structured-output incompatibility
  surfaced. A constraint that initially looked like an API limitation turned out to be the
  thing that forced the correct architecture — separating grounding from composition is what
  makes the accuracy guarantee verifiable, and a single-pass design would have produced
  model-authored citations, which are exactly as fabricable as the claims they purport to
  support. The recurring lesson across R3, R5, R6, and R7 is the same: every constitutional
  guarantee that ended up trustworthy is enforced by deterministic code or a database
  privilege, and every one that would have rested on model behaviour alone was restructured
  until it did not.

## Evaluation notes (flywheel)

- Failure modes observed: (1) `update-agent-context.ps1` reported success while writing
  nothing — a silent no-op that would have left the agent context wrong had the output not
  been verified; caught by grepping for the values the script claimed to add. (2) Both
  PowerShell scaffold scripts return exit 128 from internal `git` calls in this non-git
  repository while still succeeding — exit status is unreliable here, JSON output is the
  signal. (3) Initial instinct was to reach for pgvector/RAG by reflex; interrogating the
  actual retrieval question (single client, known scope) showed it would have degraded the
  grounding guarantee, not improved it.
- Graders run and results (PASS/FAIL): Constitution gate PASS (8/8); OpenAPI parse PASS;
  template-residue PASS; clarification-residue PASS; API-currency check PASS (skill loaded
  before writing any model configuration).
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): During `/sp.tasks`, ensure the evaluation-harness
  tasks (R13) are sequenced **before** the DT3 credit-memo tasks, not after. DT3 is the
  highest-stakes output, and shipping it before the fabricated-figure gate is measurable would
  invert the risk ordering the spec deliberately established.
