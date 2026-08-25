# Implementation Plan: AI-Powered Client Documentation

**Branch**: `001-ai-client-documentation` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md) v1.1
**Input**: Feature specification from `/specs/001-ai-client-documentation/spec.md`
**Constitution**: v1.0.0 — `.specify/memory/constitution.md`

## Summary

Build a web application that drafts corporate client documentation for Warba Bank
Relationship Managers, where every factual claim is traceable to a source, every unavailable
fact is visibly marked as missing, every draft passes a deterministic Shariah screen before a
human sees it, and no document reaches an approved state without an explicit act by the named
RM who owns the relationship.

The technical approach rests on one core decision: **two-pass generation through a validated
Evidence Ledger** (research.md R3). A Grounding Pass reads the sources with native citations
enabled and produces a ledger of claims, each bound to a verbatim excerpt and a page or
character locator. A Composition Pass then writes the document from the ledger alone — it
never sees the raw sources — under a structured-output schema that forces every section to
carry either evidence references or explicit gap markers. A deterministic validation layer
then rejects any content whose evidence references do not resolve, and any numeric literal
that appears nowhere in the ledger.

This is what turns "minimise hallucinations" from an aspiration into a machine-checkable
property. The model cannot cite what is not in the ledger, and the ledger is built from actual
document spans. Everything else in this plan — the deterministic Shariah gate, the hash-chained
audit trail, the approval state machine — follows the same pattern: **put the guarantee in
deterministic code, and use the model for the part that genuinely needs judgement.**

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, `anthropic` SDK,
python-docx, WeasyPrint · React 18, Vite, TanStack Query
**Storage**: PostgreSQL 16 — relational, JSONB for section payloads, no vector extension (R4)
**Testing**: pytest (unit / integration / contract) + a dedicated grounding evaluation
harness (R13)
**Target Platform**: Linux server (containerised); modern desktop browsers
**Project Type**: Web application — `backend/` + `frontend/`
**Model**: `claude-opus-5`, adaptive thinking, `effort: high`, streaming (R2)
**Performance Goals**: interactive actions < 3s perceived; call report first draft < 30s;
client profile < 45s (NFR-PERF-01/02)
**Constraints**: Fail closed on any failure; no real client data anywhere; audit trail
immutable at the database privilege level; core journey ≤ 5 interactions
**Scale/Scope**: MVP demonstrated at single-RM portfolio scale (~50 synthetic clients);
3 committed document types; 4 roles; no architectural ceiling on the corporate book

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

### Initial evaluation (pre-research)

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Banking-Grade Security & Compliance | ✅ PASS | Server-side generation; RBAC; env-var secrets |
| II | Shariah-Governance Readiness | ⚠️ CONDITIONAL | Needs a screening mechanism that is not model-dependent → resolved by R5 |
| III | Human-in-the-Loop | ✅ PASS | Approval as an explicit endpoint; no scheduled writer |
| IV | Accuracy Over Speed | ⚠️ CONDITIONAL | Needs a verifiable grounding mechanism → resolved by R3 |
| V | Simple, Fast UX | ✅ PASS | 5-interaction journey; streaming |
| VI | Modular & Scalable | ⚠️ CONDITIONAL | Needs a provider abstraction → resolved by R9, with a stated limit |
| VII | No Real Client Data | ✅ PASS | Synthetic fixtures only |
| VIII | Total Auditability | ⚠️ CONDITIONAL | Needs enforced immutability → resolved by R6 |

Four conditionals, all resolved in Phase 0. None became a violation.

### Post-design re-evaluation

| # | Principle | Status | Mechanism | Verified by |
|---|-----------|--------|-----------|-------------|
| I | Banking-Grade Security & Compliance | ✅ PASS | TLS; JWT + portfolio-scoped RBAC in one shared dependency (R11); `pydantic-settings` env vars, `.env.example` placeholders only (R14); structured logs carry identifiers not content; **fail-closed** on every failure path — generation returns 4xx/5xx and no document; uploaded content structurally confined to the data channel (R7) | FR-001, FR-007, FR-037, FR-042; NFR-SEC-01..07 |
| II | Shariah-Governance Readiness | ✅ PASS | Deterministic lexicon gate over a reviewable `vocabulary.yaml`, applied **before display** and binding; advisory semantic layer that can only add findings, never clear a block (R5); `shariah_status` column defaults to `PENDING_REVIEW` and the system has **no code path that sets `CLEARED`** | FR-015..019; DT3 scenarios 1–5 |
| III | Human-in-the-Loop | ✅ PASS | `POST /documents/{id}/approve` is the only transition into `APPROVED`; requires RM role **and** portfolio ownership, a matching `content_hash`, `confirm_reviewed: true`, and zero unresolved gaps; `APPROVED` is terminal; **no timer, scheduler, or default writes `status`** | FR-025..028; SC-015; US1 scenarios 4–5 |
| IV | Accuracy Over Speed | ✅ PASS | Two-pass generation through the Evidence Ledger (R3); every `evidence_ref` validated against the ledger; **every numeric literal must trace to a claim or generation fails closed**; gap markers as a first-class state; per-section confidence flags; `effort: high` | FR-009..013; SC-004 (release gate), SC-005, SC-006 |
| V | Simple, Fast UX | ✅ PASS | Five-interaction core journey; streaming generation with honest progress; plain banking language in every error body; AI-generated label always present | FR-020; NFR-UX-01..04; NFR-PERF-01..03; SC-009 |
| VI | Modular & Scalable | ✅ PASS (1 documented limit) | Layered `api → services → ports → adapters`; `GenerationPort` protocol with `AnthropicAdapter` (R9); new document types via template + prompt + schema, no engine change; prompts, templates, and vocabulary are versioned artifacts | FR-043, FR-044; NFR-SCA-01..05; SC-016. **Limit recorded in Complexity Tracking** |
| VII | No Real Client Data | ✅ PASS | All fixtures synthetic; `Client.is_synthetic` carries a **database CHECK constraint** — a non-synthetic row cannot be inserted; no live system integration | FR-041; Assumption A2 |
| VIII | Total Auditability | ✅ PASS | `audit_event` hash-chained (`event_hash = SHA256(prev_hash ‖ canonical_json)`); application role granted **INSERT + SELECT only**, `UPDATE`/`DELETE` never granted; every FR-030 field captured; `/audit/verify` recomputes the chain; approval snapshots approver name and role | FR-029..036; SC-012..014; US4 scenarios 1–4 |

**Gate result: PASS.** Eight of eight. One documented limitation under Complexity Tracking; no
unjustified violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-ai-client-documentation/
├── plan.md              # This file
├── spec.md              # Feature specification v1.1
├── research.md          # Phase 0 — R1..R14
├── data-model.md        # Phase 1 — 13 entities, state machine, validation rules
├── quickstart.md        # Phase 1 — setup and guarantee demonstrations
├── contracts/
│   └── openapi.yaml     # Phase 1 — API contract
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/sp.tasks — NOT created by /sp.plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── main.py
│   ├── config.py                    # pydantic-settings; no secret ever literal
│   ├── api/v1/                      # routers: auth, clients, sources, documents,
│   │                                #          sections, approval, export, audit
│   ├── auth/
│   │   ├── jwt.py
│   │   └── dependencies.py          # ONE portfolio-scoping dependency — a new
│   │                                # endpoint cannot forget it (R11)
│   ├── clients/
│   │   ├── models.py
│   │   └── context_assembler.py     # deterministic, client-scoped (R4)
│   ├── documents/
│   │   ├── models.py
│   │   ├── schemas/                 # Pydantic section models = structured-output contracts
│   │   ├── state_machine.py         # the ONLY writer of Document.status
│   │   ├── generation_service.py    # orchestrates Pass A → Pass B → validate → screen
│   │   └── validators.py            # evidence resolution + numeric-literal tracing
│   ├── evidence/
│   │   ├── models.py
│   │   └── ledger_builder.py        # native citations → EvidenceLedger
│   ├── screening/
│   │   ├── deterministic.py         # the binding gate (R5)
│   │   └── semantic.py              # advisory only; can never clear a block
│   ├── audit/
│   │   ├── models.py
│   │   ├── recorder.py              # append-only writer
│   │   └── chain.py                 # hash chain + verification
│   ├── export/
│   │   ├── docx_renderer.py
│   │   └── pdf_renderer.py          # both render from the same validated model (R12)
│   ├── ports/
│   │   └── generation_port.py       # Protocol — business logic depends on THIS
│   ├── adapters/
│   │   └── anthropic_adapter.py     # the ONLY module importing `anthropic`
│   └── fixtures/
│       └── seed.py
├── config/
│   ├── vocabulary.yaml              # versioned; Shariah-reviewable without reading code
│   ├── templates/                   # per-document-type section definitions
│   └── prompts/                     # versioned prompt artifacts
├── fixtures/synthetic/              # clients, records, statements, notes, adversarial cases
├── scripts/create_roles.sql         # the INSERT+SELECT-only audit grant
├── migrations/                      # Alembic
└── tests/
    ├── unit/
    ├── integration/                 # stubbed GenerationPort — no model calls in CI
    ├── contract/
    └── evaluation/                  # grounding harness — the release gates (R13)

frontend/
├── src/
│   ├── api/
│   ├── components/
│   │   ├── ContextPreview.tsx       # what the system knows, before it writes (FR-003/004)
│   │   ├── DocumentReview.tsx
│   │   ├── SectionCard.tsx          # content + citations + confidence flag
│   │   ├── GapMarker.tsx            # visible, unmissable, blocks approval
│   │   ├── EvidenceInspector.tsx    # verbatim excerpt + locator (FR-024)
│   │   └── ApprovalDialog.tsx       # deliberate act; echoes content_hash
│   ├── pages/                       # Portfolio, Generate, Review, AuditLifecycle
│   └── types/                       # generated from openapi.yaml
└── tests/
```

**Structure Decision**: Web application (backend + frontend). The layered backend directly
implements NFR-SCA-01 and Principle VI: `api → services → ports → adapters`, with dependencies
pointing inward. `adapters/anthropic_adapter.py` is the single module permitted to import the
`anthropic` package — a lint rule enforces this, so provider substitutability is verified
mechanically rather than by intent.

Three modules are deliberately isolated because they carry constitutional guarantees and must
be independently testable and reviewable: `screening/deterministic.py` (Principle II),
`documents/validators.py` (Principle IV), and `audit/chain.py` (Principle VIII).

## Phase Status

| Phase | Output | Status |
|-------|--------|--------|
| 0 — Research | `research.md` (R1–R14) | ✅ Complete — no NEEDS CLARIFICATION remain |
| 1 — Design | `data-model.md`, `contracts/openapi.yaml`, `quickstart.md` | ✅ Complete |
| 1 — Agent context | `CLAUDE.md` technology section | ✅ Updated |
| 2 — Tasks | `tasks.md` | ⏭️ Not started — run `/sp.tasks` |

## Complexity Tracking

> Filled only where the Constitution Check surfaced something requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| **Provider abstraction is partial**: `GenerationPort` is provider-neutral in contract, but the Grounding Pass depends on Anthropic's native document citations, which are not a portable capability (R9) | Native citations return `cited_text` with page/character locators straight from the source. This is the mechanism that makes the Evidence Ledger trustworthy. A provider-neutral substitute (span matching, chunk-offset attribution) yields coarser locators and reintroduces exactly the fabricated-citation risk the two-pass design exists to eliminate — trading a Principle IV guarantee for a Principle VI convenience | A fully portable grounding implementation would have to re-derive locators after generation, which is inference about where a claim came from rather than a record of it. **Mitigation**: business logic depends only on the port; `anthropic` is importable from one adapter module and a lint rule enforces it; swapping providers means writing one adapter and re-running the evaluation harness, not rewriting the application. NFR-SCA-04's actual requirement — that business logic never depends on a provider — is met |
| **Two model calls per document instead of one** (R3) | The grounding guarantee requires that the composing model never sees the raw sources, so it cannot cite anything absent from the ledger. One call cannot do this: Anthropic citations and `output_config.format` are mutually exclusive (400), and we need both guaranteed schema coverage and verifiable citations | A single call with model-authored citation strings lets the model invent its own citations, which inverts the purpose. Post-hoc verification via a third call is both slower and still probabilistic, where ledger validation is deterministic. The latency cost sits inside the NFR-PERF-02 envelope because both passes stream |

Neither entry is a constitutional violation. Both are deliberate trades recorded so a reviewer
can see the reasoning rather than rediscover it.

## Risks

| Risk | Blast radius | Mitigation / kill switch |
|------|--------------|--------------------------|
| Grounding quality falls short of the zero-fabrication gate on the credit memo (DT3) | The highest-stakes document type is unusable | DT3 is sequenced last (P3) precisely so grounding is proven on DT1/DT2 first. The evaluation harness gates release per document type — DT3 can be withheld while DT1/DT2 ship |
| Two-pass latency exceeds the NFR-PERF-02 envelope on large uploads | RM experience degrades; Principle V pressure | Both passes stream. If the envelope is breached, the correct response is honest progress and a longer wait, never relaxing validation — Principle IV is explicit that speed never buys accuracy |
| Vocabulary is incomplete, so a prohibited term slips the deterministic gate | A non-compliant draft reaches an RM | The semantic layer is defence in depth for exactly this. Vocabulary is versioned and every screening records the version applied, so a gap is diagnosable and every past decision reproducible |

## Architectural Decisions for ADR Consideration

Three decisions meet the significance test — long-term impact, multiple viable alternatives
evaluated, cross-cutting influence on system design:

1. **Two-pass generation with a validated Evidence Ledger** (R3) — the grounding architecture
   the entire accuracy guarantee rests on.
2. **Deterministic-first Shariah screening** (R5) — why a NON-NEGOTIABLE control is a word
   list rather than a model judgement.
3. **Hash-chained audit with database-privilege immutability** (R6) — tamper-evident rather
   than tamper-discouraged.

A fourth is worth noting as a deliberate *non*-decision: **no vector database** (R4). Rejecting
the reflexive RAG default is itself a significant architectural choice, and the reasoning
deserves recording so a future contributor does not add one by default.
