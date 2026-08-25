# Phase 0: Research & Technical Decisions

**Feature**: 001-ai-client-documentation
**Date**: 2026-08-21
**Constitution**: v1.0.0
**Spec**: [spec.md](./spec.md) v1.1

This document resolves every open technical decision required before design. Each entry
records the decision, its rationale, the alternatives rejected, and the constitutional
principle it serves.

---

## R1 — Application Architecture

**Decision**: Web application, split backend and frontend.
Python 3.12 + FastAPI backend; React 18 + TypeScript + Vite frontend.

**Rationale**:

- The generation, grounding, screening, and audit logic all belong server-side. No model call
  and no client data may originate in the browser (Principle I).
- Python is where the AI ecosystem lives — the official Anthropic SDK, Pydantic for the
  structured-output contracts this design depends on, and PDF tooling.
- FastAPI gives Pydantic-native request/response validation, which matters here because the
  same Pydantic models define both the API contract and the structured-output schema for
  document generation. One schema, two uses, no drift.
- The layer separation required by Principle VI maps cleanly onto FastAPI routers → services
  → adapters.

**Alternatives considered**:

- **Next.js full-stack** — one language, faster scaffolding. Rejected: pushes generation
  logic into a Node runtime where the Anthropic Python SDK, Pydantic, and PDF extraction
  libraries are weaker, and blurs the browser/server boundary that Principle I depends on.
- **Streamlit** — fastest possible hackathon demo. Rejected: cannot express the review UI
  (per-section citations, inline editing, gap resolution) and offers no path to production.
  Principle VI requires the prototype to be a first increment, not a throwaway.
- **Python monolith with server-rendered templates** — fewer moving parts. Rejected: the
  review-and-edit surface is genuinely interactive and would fight the model.

**Serves**: Principle I, Principle VI.

---

## R2 — Model Selection & Invocation Parameters

**Decision**: `claude-opus-5` via the official `anthropic` Python SDK.
Adaptive thinking enabled, effort `high`, streaming for all generation calls.

```python
client.messages.create(
    model="claude-opus-5",
    max_tokens=64000,
    thinking={"type": "adaptive"},
    output_config={"effort": "high"},
    ...
)
```

**Rationale**:

- **Model**: Opus 5 is the most capable model in the current family. Principle IV makes
  accuracy the binding constraint, and this is a domain where a wrong number in a credit memo
  is a real harm. Cost per document is negligible against RM hourly cost.
- **Adaptive thinking**: on by default for Opus 5; `budget_tokens` is removed on this model
  and returns 400. Extraction and grounding are exactly the kind of careful reasoning tasks
  adaptive thinking targets.
- **Effort `high`**: the accuracy/cost tradeoff resolves toward accuracy under Principle IV.
  `high` is the sweet spot; `max` is reserved for the credit memo composition pass if
  evaluation shows it is needed.
- **Streaming**: generation runs long and `max_tokens` is large. The SDKs require streaming
  at high token counts to avoid HTTP timeouts, and NFR-PERF-03 forbids a frozen screen —
  streaming satisfies both with one mechanism. Use `stream.get_final_message()` where the
  service does not need individual events.
- **1M context window**: this is what makes R4 (no vector database) viable.

**Alternatives considered**:

- **`claude-sonnet-5`** — cheaper, faster. Rejected as the default: Principle IV is explicit
  that speed never buys accuracy. Sonnet remains the fallback if evaluation shows parity.
- **`budget_tokens` thinking control** — removed on Opus 5; sending it returns 400.
- **Non-streaming with lower `max_tokens`** — risks truncating a document mid-section, which
  under a fail-closed policy means discarding the whole generation.

**Serves**: Principle IV, Principle V.

---

## R3 — The Grounding Architecture: Two-Pass Generation

**Decision**: Split generation into two distinct model calls — a **Grounding Pass** and a
**Composition Pass** — connected by an intermediate **Evidence Ledger**.

**The constraint that forces this**: Anthropic's native citations (`citations: {enabled: true}`
on a `document` content block) return `cited_text` plus a precise `char_location` or
`page_location` for every claim. That is exactly the mechanism FR-011 needs. But **citations
are incompatible with `output_config.format`** — combining them returns a 400. And FR-009
(every template section populated or gap-marked) needs guaranteed schema conformance, which is
exactly what structured outputs provide.

We need both. One call cannot have both. So we use two.

**Pass A — Grounding**

- Input: uploaded documents and pasted notes as `document` content blocks with
  `citations: {enabled: true}`. Structured client records passed as text.
- No `output_config.format`.
- Output: prose claims, each carrying a native citation with `cited_text` and a
  char/page location.
- Post-processing normalises these into an **Evidence Ledger**: a list of
  `{claim_id, claim_text, source_type, source_id, locator, verbatim_excerpt}`.

**Pass B — Composition**

- Input: the Evidence Ledger (structured text — no `document` blocks, so no citation
  conflict), plus the document template and approved vocabulary.
- `output_config.format` bound to a per-document-type Pydantic model via
  `client.messages.parse()`.
- Output: a validated object where every section carries `content`, a list of
  `evidence_refs` (claim_ids), and a list of `gaps`.

**Post-Pass validation (deterministic, not model-based)**:

1. Every `evidence_ref` must resolve to a real claim_id in the ledger. An unresolvable
   reference means the section is unsourced → the section is rejected and converted to a gap.
2. Every template-mandated section must be present with either content or a gap.
3. Numeric literals appearing in section content must appear in the ledger. A number that
   exists nowhere in the evidence is a fabrication → generation fails closed.

**Rationale**: This is the concrete mechanism by which Principle IV stops being aspirational.
The model cannot cite what is not in the ledger, because Pass B never sees the raw documents.
The ledger is the bottleneck, and it is machine-checkable. Check 3 in particular is what makes
SC-004 ("zero fabricated financial figures") a testable release gate rather than a hope.

**Alternatives considered**:

- **Single call with structured output, citations as model-authored strings** — simpler and
  one round trip. Rejected outright: the model would author its own citation strings, which
  means the citation itself can be hallucinated. That inverts the entire purpose.
- **Single call with citations, parse prose into sections afterward** — keeps native
  citations but loses guaranteed section coverage; parsing prose back into a schema is
  brittle and would silently drop sections.
- **Post-hoc verification of a single-pass output against sources** — a third model call to
  check the second. Rejected: adds latency and still rests on a probabilistic check, where
  the ledger approach gives a deterministic one.

**Cost**: two model calls per document instead of one, and higher latency. Accepted under
Principle IV, and within the NFR-PERF-02 envelope (30s call report / 45s profile) because both
passes stream.

**Serves**: Principle IV (primary), Principle VIII.

---

## R4 — Retrieval Strategy: No Vector Database in MVP

**Decision**: Deterministic, client-scoped context assembly. No embeddings, no vector store,
no chunking, no RAG pipeline.

**Rationale**:

- Every generation is scoped to **exactly one client**. The retrieval question is not "find
  relevant documents across a corpus" — it is "load this client's records and this client's
  uploaded files". That is a database query with a `WHERE client_id = ?`, not a similarity
  search.
- A single corporate client's full context — profile, facilities, interaction history, and
  a handful of uploaded statements — fits comfortably inside Opus 5's 1M context window.
- Semantic retrieval introduces a probabilistic step *upstream* of grounding. A chunk that
  retrieval failed to surface becomes an invisible gap: the model does not know the fact
  exists, so it cannot mark it missing. Deterministic assembly means the RM sees the complete
  candidate context before generation (FR-003) and can deselect from it (FR-004) — which is
  only meaningful if the set is knowable in advance.
- It removes an entire subsystem — embedding model, vector store, chunking strategy, index
  freshness — from the MVP. Principle VI favours the smallest viable architecture.

**When this stops being true**: a client with hundreds of documents, or cross-client search.
Both are out of MVP scope. The `ContextAssembler` interface is the seam where retrieval would
later be introduced without disturbing the two-pass generation design.

**Alternatives considered**:

- **pgvector + chunked embedding retrieval** — the reflexive default for document AI.
  Rejected for MVP as unnecessary complexity that actively harms the grounding guarantee at
  this scale.
- **Full-text search over client documents** — same objection, less benefit.

**Serves**: Principle VI (primary), Principle IV.

---

## R5 — Shariah Screening: Deterministic Gate First

**Decision**: A two-layer screen. Layer 1 is a deterministic lexicon check that is the
binding gate. Layer 2 is a model-based semantic review that can only *add* findings.

**Layer 1 — Deterministic (authoritative)**

- A versioned YAML vocabulary: `prohibited_terms` (interest, riba, conventional loan,
  overdraft interest, bond coupon, and sector terms), `approved_structures` (Murabaha, Ijara,
  Wakala, Musharaka, Mudaraba, Salam, Istisna'a), and `approved_terminology`.
- Case-insensitive, word-boundary matching over generated content, applied **before display**.
- Any hit blocks display of the draft and reports the violation (FR-016).
- Runs on inputs too, so a non-compliant client request is flagged rather than drafted
  (FR-017).

**Layer 2 — Semantic (advisory, additive)**

- A separate model call reviews the draft for structures that are non-compliant *in substance*
  while using compliant vocabulary — the case the lexicon cannot catch.
- It can raise a flag. It can never clear one.

**Rationale**: Principle II is NON-NEGOTIABLE, and a non-negotiable control cannot rest on a
probabilistic check. The deterministic layer is auditable, testable, reviewable by a
non-technical Shariah stakeholder, and produces identical results on identical input. The
model layer catches what a word list cannot, but is never the thing standing between a
violation and the RM. Fail-closed by construction: if screening errors, no draft is shown
(NFR-SEC-07).

**Alternatives considered**:

- **Model-only screening** — catches semantics, misses determinism. Rejected: cannot be a
  non-negotiable gate.
- **Lexicon-only** — fully deterministic but blind to compliant-sounding non-compliant
  structures. Rejected as insufficient alone; retained as the authoritative layer.
- **Screening only at export** — rejected: FR-015 requires screening before the RM sees the
  draft, so a violation never reaches a human as apparently-valid content.

**Serves**: Principle II (primary), Principle I.

---

## R6 — Immutable Audit Trail: Hash-Chained, Append-Only, Enforced at Two Levels

**Decision**: A single `audit_event` table, append-only, with each row carrying the SHA-256
hash of the previous row (hash chaining). Immutability enforced at both the application layer
and the database privilege layer.

**Mechanism**:

- Each event stores `prev_hash`, and `event_hash = SHA256(prev_hash || canonical_json(event))`.
- Tampering with any historical row breaks the chain from that row forward, and a chain
  verification endpoint detects it. This is what makes the trail *tamper-evident*, not merely
  *tamper-discouraged*.
- **Database privilege**: the application role is granted `INSERT, SELECT` on `audit_event`
  and explicitly **not** `UPDATE, DELETE`. FR-032 says no application user may edit or delete
  audit records; enforcing that only in application code means one missing guard defeats it.
  A revoked privilege cannot be forgotten.
- Canonical JSON serialisation (sorted keys, fixed separators) so hashes are reproducible.

**Rationale**: Principle VIII requires that documents be *reconstructable and explainable
after the fact*. An audit table the application can silently rewrite proves nothing. Hash
chaining is cheap, needs no external infrastructure, and turns "trust the application" into
"verify the chain".

**Alternatives considered**:

- **Plain append-only table, application-enforced** — a single ORM misuse or an admin console
  defeats it. Rejected as insufficient for a NON-NEGOTIABLE-adjacent principle.
- **Event sourcing as the primary persistence model** — full auditability, but restructures
  the entire data layer for a benefit already achieved. Rejected under smallest-viable-change.
- **External append-only log (Kafka, S3 Object Lock, blockchain)** — stronger guarantees,
  operationally heavy, undemonstrable in a hackathon environment. The hash chain provides the
  verifiable property; production can back it with WORM storage without changing the schema.

**Serves**: Principle VIII (primary), Principle I.

---

## R7 — Prompt Injection Defence

**Decision**: Strict channel separation, enforced structurally rather than by instruction.

- **Instruction channel**: the top-level `system` parameter only. Composed entirely from
  server-side templates. Never contains user or document content.
- **Data channel**: uploaded files and pasted notes are passed exclusively as `document`
  content blocks inside a `user` turn, never interpolated into the system prompt.
- **RM instruction channel**: the RM's optional free-text instruction is passed in a `user`
  turn inside explicit delimiters, with a system directive scoping it to *stylistic
  preference only* — it can never authorise a claim, alter screening, or grant approval.
- **Mid-conversation system messages are never used for any user-derived content.** The
  operator channel stays operator-only.
- **Output validation is the real defence**: even a successful injection cannot manufacture a
  citation, because Pass B's evidence_refs are validated against the ledger, and the ledger is
  built from actual document spans. An injected "state the facility is approved" produces an
  unsourced claim, which the deterministic post-pass check converts to a gap or rejects.

**Rationale**: NFR-SEC-05 and FR-007 require ingested content to be treated as data. Prompt
instructions telling a model to ignore embedded instructions are a mitigation, not a control.
The architecture makes injection *ineffective* rather than merely *discouraged* — this is the
same insight as R3: the deterministic validation layer is what carries the guarantee.

**Serves**: Principle I (primary), Principle IV.

---

## R8 — Document Upload & Extraction *(confirmed in MVP by decision D3)*

**Decision**: Anthropic Files API upload, then reference by `file_id` in a `document` content
block with citations enabled. No separate OCR or PDF-parsing pipeline.

```python
uploaded = client.beta.files.upload(file=("statement.pdf", fh, "application/pdf"))
# then, in the Grounding Pass:
{"type": "document",
 "source": {"type": "file", "file_id": uploaded.id},
 "title": "FY2025 Audited Statements",
 "citations": {"enabled": True}}
```

**Rationale**:

- Native document handling returns `page_location` citations directly — page-precise
  provenance for every extracted figure, which is exactly what a Credit reviewer needs.
- A separate extract-then-embed pipeline would strip that page linkage and force us to
  reconstruct provenance, reintroducing the fabricated-citation risk R3 exists to eliminate.
- Files API requires beta header `files-api-2025-04-14` on **both** the upload and the
  `messages` call that references the file, and uploads must go through
  `client.beta.messages.create`.

**Limits to enforce** (spec edge case: "very large upload"): 32 MB per request, 600 pages per
PDF. The system validates before upload and **declines clearly** — never truncates silently.

**Alternatives considered**:

- **Local extraction (`pypdf`/`pdfplumber`) then text-only prompting** — no vendor dependency
  for extraction, but loses page-location citations and adds an OCR failure mode for scanned
  statements. Rejected: provenance is the point.
- **Base64 inline documents** — works, but re-uploads the file on every call. The Files API
  uploads once and references by id across the grounding pass and any regeneration.

**Serves**: Principle IV, Principle VIII.

---

## R9 — Provider Abstraction & Its Honest Limits

**Decision**: A `GenerationPort` protocol expressing the two-pass contract in
provider-neutral terms, with `AnthropicAdapter` as the MVP implementation.

```python
class GenerationPort(Protocol):
    def ground(self, sources: list[Source], scope: GroundingScope) -> EvidenceLedger: ...
    def compose(self, ledger: EvidenceLedger, template: DocumentTemplate,
                schema: type[BaseModel]) -> BaseModel: ...
    def screen_semantic(self, draft: str, vocabulary: Vocabulary) -> list[ScreeningFinding]: ...
```

**The honest tradeoff, stated plainly**: native citations are an Anthropic capability. The
*port contract* is provider-neutral — it promises an Evidence Ledger of claims with source
locators. The *mechanism* is not portable. A different provider's adapter would have to
produce that ledger another way (span matching, chunk-offset attribution), and would likely
produce coarser locators.

This is a real limitation and it is recorded rather than hidden. What NFR-SCA-04 actually
requires is that **business logic never depends on a provider**, and that is satisfied: the
services, screening, validation, audit, and API layers depend only on the port. Swapping
providers means writing one adapter and re-running the grounding evaluation set — not
rewriting the application.

**Serves**: Principle VI.

---

## R10 — Persistence

**Decision**: PostgreSQL 16, accessed via SQLAlchemy 2.0 with Alembic migrations.
No vector extension (see R4).

**Rationale**: Relational fits the domain — clients, documents, sections, versions, audit
events are all strongly relational with real integrity constraints. Postgres provides the
row-level privilege control R6 depends on, JSONB for the flexible per-document-type section
payloads, and transactional integrity so a generation event and its audit record commit
together or not at all.

**Alternatives considered**:

- **SQLite** — zero setup, ideal for a demo. Rejected: no meaningful role/privilege model, so
  the database-level immutability guarantee in R6 is unavailable.
- **MongoDB** — flexible section documents. Rejected: the domain is relational, and the audit
  guarantee wants transactional writes.

**Serves**: Principle VI, Principle VIII.

---

## R11 — Authentication & Authorisation

**Decision**: JWT bearer tokens, four seeded roles, portfolio-scoped authorisation enforced
in a single dependency.

| Role | Permissions |
|------|-------------|
| `RM` | Own portfolio only. Generate, edit, regenerate, reject, **approve**. |
| `TEAM_LEAD` | Read-only across the team's portfolios. No approval. |
| `COMPLIANCE` | Read audit records and documents across all portfolios. No editing, no approval. |
| `SHARIAH_REVIEWER` | Read documents and Shariah status. No editing, no approval. |

**Key rule**: `approve` is granted to the `RM` role **only**, and only for a document on a
client in that RM's own portfolio. Principle III places accountability on a named human;
allowing a Team Lead or an administrator to approve would break the accountability chain that
the whole design rests on.

Portfolio scoping is applied in one shared dependency rather than per-endpoint, so a new
endpoint cannot forget it.

**Serves**: Principle I, Principle III.

---

## R12 — Export

**Decision**: `python-docx` for DOCX, WeasyPrint for PDF, both rendered from the same
validated section model.

Every export embeds the approval record (approver, timestamp, content hash), the Shariah
review status, and an AI-assisted attribution line (FR-036).

**Rationale**: Bank documentation workflows are DOCX-centric; Credit reviewers annotate in
Word. Rendering both formats from the same validated object rather than from HTML avoids
format drift between what the RM approved and what is exported — the approved content hash
must match the exported content.

**Serves**: Principle VIII.

---

## R13 — Testing & Evaluation Strategy

**Decision**: Conventional test pyramid plus a dedicated **grounding evaluation harness**.

- **Unit** (`pytest`): screening lexicon, ledger validation, hash chain, gap detection,
  numeric-literal verification.
- **Integration**: full generation pipeline against a stubbed `GenerationPort` — deterministic,
  no model calls, runs in CI.
- **Contract**: OpenAPI schema conformance.
- **Evaluation harness** (the one that matters): a curated set of synthetic cases with
  known-correct outputs *and known gaps*, scoring:
  - fabricated-figure rate → must be **zero** (SC-004, release gate)
  - citation resolution rate → must be **100%** (SC-005)
  - gap detection recall → must be **100%** (SC-006)
  - prohibited-terminology rate → must be **zero** (SC-007)
  - injection resistance → adversarial fixtures with embedded instructions

**Rationale**: Standard tests verify the code does what it says. Only the evaluation harness
verifies the *model-dependent* guarantees, and those are precisely the guarantees Principle IV
makes release-blocking. Cases with deliberately absent data are as important as cases with
present data — an assistant that invents plausible text for missing data fails silently, and
only a known-gaps fixture catches it.

**Serves**: Principle IV, Principle VIII.

---

## R14 — Secrets & Configuration

**Decision**: Environment variables via `pydantic-settings`, `.env` for local development,
`.env.example` committed with placeholders only. Never a real key in source control.

Credential resolution follows the SDK's own order — `ANTHROPIC_API_KEY`, then
`ANTHROPIC_AUTH_TOKEN`, then an `ant auth login` profile — so a zero-argument
`anthropic.Anthropic()` client works in every environment without branching.

**Serves**: Principle I.

---

## Resolved Unknowns Summary

| Unknown | Resolution |
|---------|-----------|
| Language / framework | Python 3.12 + FastAPI; React 18 + TypeScript |
| Model | `claude-opus-5`, adaptive thinking, effort `high`, streaming |
| How to guarantee grounding | Two-pass generation with a validated Evidence Ledger (R3) |
| Retrieval approach | Deterministic client-scoped assembly; no vector DB (R4) |
| Shariah screening | Deterministic lexicon gate + advisory semantic layer (R5) |
| Audit immutability | Hash chain + DB privilege revocation (R6) |
| Injection defence | Channel separation + ledger validation (R7) |
| Document extraction | Files API + native citations (R8) |
| Provider portability | `GenerationPort` protocol; limits stated honestly (R9) |
| Storage | PostgreSQL 16 + SQLAlchemy 2.0 + Alembic (R10) |
| Auth model | JWT, 4 roles, approval restricted to owning RM (R11) |
| Export | python-docx + WeasyPrint from one validated model (R12) |
| Test strategy | Test pyramid + grounding evaluation harness (R13) |
| Secrets | Environment variables; nothing committed (R14) |

**No unresolved NEEDS CLARIFICATION items remain.**
