# Phase 1: Data Model

**Feature**: 001-ai-client-documentation
**Date**: 2026-08-21
**Depends on**: [research.md](./research.md), [spec.md](./spec.md) §Key Entities

All persisted data in the prototype is synthetic (Principle VII, FR-041).

---

## Entity Overview

```
User ──owns──< Client ──has──< Document ──has──< DocumentVersion ──has──< DocumentSection
                  │                │                                          │
                  │                ├──has──< SourceDocument (uploaded)         └──refs──> EvidenceClaim
                  │                ├──has──< EvidenceLedger ──has──< EvidenceClaim
                  │                ├──has──< ApprovalRecord (0..1)
                  │                └──has──< ScreeningResult
                  │
                  └──has──< ClientRecord (profile / facility / interaction fixtures)

AuditEvent ──(hash chain, references everything, owned by nothing)
DocumentTemplate ──configures──> Document
Vocabulary ──governs──> ScreeningResult
```

---

## 1. User

The accountable human. Principle III rests on this entity being a real, named person.

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `email` | string | unique, not null |
| `full_name` | string | not null |
| `role` | enum | `RM` \| `TEAM_LEAD` \| `COMPLIANCE` \| `SHARIAH_REVIEWER` |
| `team_id` | UUID | nullable; groups RMs under a TEAM_LEAD |
| `is_active` | bool | default true |
| `created_at` | timestamptz | not null |

**Rules**

- Only `role = RM` may approve a document (FR-026, R11).
- An inactive user cannot authenticate or approve.

---

## 2. Client

A corporate banking client. Synthetic in all prototype environments.

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `client_reference` | string | unique; the bank-facing identifier |
| `legal_name` | string | not null |
| `trade_name` | string | nullable |
| `commercial_registration` | string | nullable — **synthetic** |
| `sector` | string | not null |
| `incorporation_date` | date | nullable |
| `relationship_since` | date | nullable |
| `owning_rm_id` | UUID | FK → User, not null |
| `kyc_status` | enum | `COMPLETE` \| `PENDING` \| `EXPIRED` |
| `is_synthetic` | bool | **not null, default true, CHECK (is_synthetic = true)** |

**Rules**

- `is_synthetic` carries a database CHECK constraint that cannot be satisfied by a non-synthetic
  record. Principle VII is NON-NEGOTIABLE, so it is enforced by the schema, not by convention.
- A user with `role = RM` may only read clients where `owning_rm_id = user.id` (FR-001).

---

## 3. ClientRecord

Structured internal-source fixtures — the deterministic context of R4. One polymorphic table
keyed by `record_type` rather than a table per source, so a new internal source category needs
no migration.

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `client_id` | UUID | FK → Client, not null, indexed |
| `record_type` | enum | `PROFILE` \| `FACILITY` \| `INTERACTION` \| `FINANCIAL_SUMMARY` \| `KYC` |
| `source_system` | enum | `CORE_BANKING` \| `CRM` \| `KYC_SYSTEM` \| `PRODUCT_CATALOGUE` \| `EXTERNAL_REGISTRY` |
| `payload` | JSONB | not null; shape varies by `record_type` |
| `effective_date` | date | nullable |
| `is_external` | bool | default false |
| `created_at` | timestamptz | not null |

**Rules**

- `is_external = true` records MUST be rendered visually distinct in generated output (FR-014).
- Records are never mutated in place; corrections create a new record with a later
  `effective_date`.

---

## 4. SourceDocument

An RM-uploaded file used as a grounding source (decision D3, R8).

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `client_id` | UUID | FK → Client, not null |
| `uploaded_by` | UUID | FK → User, not null |
| `filename` | string | not null |
| `media_type` | string | not null; `application/pdf`, `text/plain` |
| `size_bytes` | int | not null; **CHECK ≤ 33_554_432** (32 MB) |
| `page_count` | int | nullable; **CHECK ≤ 600** when present |
| `provider_file_id` | string | nullable; the Files API `file_id` |
| `content_hash` | string | SHA-256 of the uploaded bytes |
| `trust_level` | enum | **`UNTRUSTED`** — constant; there is no other value |
| `uploaded_at` | timestamptz | not null |

**Rules**

- `trust_level` is a single-valued enum by design. It exists to make FR-007 legible in the
  schema: uploaded content is data, never instruction (R7). A field that could be set to
  `TRUSTED` would be a field someone eventually sets.
- Size and page limits are validated **before** upload; violations are declined with a clear
  message, never silently truncated (spec edge case).

---

## 5. DocumentTemplate

The versioned, configurable definition of a document type. This entity is what makes
NFR-SCA-01 true — a new document type is a row plus a template file, not a code change.

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `document_type` | enum | `CALL_REPORT` \| `CLIENT_PROFILE` \| `CREDIT_MEMO_NARRATIVE` \| `KYC_SUMMARY` |
| `version` | string | semver; unique with `document_type` |
| `display_name` | string | not null |
| `section_definitions` | JSONB | ordered list: `{key, title, required, guidance, max_words}` |
| `required_inputs` | JSONB | e.g. `["meeting_notes"]` for `CALL_REPORT` |
| `screening_profile` | string | FK-by-name → Vocabulary profile |
| `prompt_template_ref` | string | path to the versioned prompt artifact |
| `is_active` | bool | default true |

**Rules**

- Templates are immutable once used by any document; a change creates a new `version`.
- Every approved document links to the exact template version that produced it (FR-033).

---

## 6. Document

A generated instance. Owns the lifecycle state Principle III governs.

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `client_id` | UUID | FK → Client, not null |
| `document_type` | enum | as above |
| `template_id` | UUID | FK → DocumentTemplate, not null |
| `created_by` | UUID | FK → User, not null |
| `status` | enum | `DRAFT` \| `UNDER_REVIEW` \| `REJECTED` \| `APPROVED` |
| `shariah_status` | enum | **default `PENDING_REVIEW`** \| `CLEARED` \| `FLAGGED` |
| `current_version_id` | UUID | FK → DocumentVersion, nullable |
| `created_at` | timestamptz | not null |

### State transitions

```
            generate            edit / regenerate
   (none) ──────────> DRAFT ──────────────────────> DRAFT
                        │                              │
                        │ submit for review            │
                        v                              │
                   UNDER_REVIEW <───────────────────────┘
                     │       │
             reject  │       │ approve  (RM only, owning portfolio,
                     v       │           zero unresolved gaps)
                 REJECTED    v
                     │    APPROVED  ← terminal
                     │
                     └──> regenerate ──> DRAFT
```

**Rules**

- `APPROVED` is terminal. An approved document is never edited; a correction is a new document
  linked to the original.
- The transition into `APPROVED` requires **all** of:
  1. actor role is `RM`, and `client.owning_rm_id = actor.id` (FR-026, R11);
  2. zero unresolved gaps across all sections (FR-025);
  3. the current version passed screening (FR-015);
  4. an explicit approval request carrying the version's `content_hash` — the RM approves a
     *specific* version, not "the document" (FR-026).
- No transition into `APPROVED` exists that is triggered by time, inactivity, or any actor
  other than a human request (FR-027). There is no scheduled job that touches `status`.
- `shariah_status` is set to `PENDING_REVIEW` on creation and is **never** set to `CLEARED` by
  the system (Principle II — the system prepares documents for review, it does not clear them).

---

## 7. DocumentVersion

An immutable snapshot. Every generation, edit, and regeneration creates one (FR-029).

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `document_id` | UUID | FK → Document, not null |
| `version_number` | int | not null; unique with `document_id` |
| `origin` | enum | `GENERATED` \| `REGENERATED_SECTION` \| `RM_EDITED` |
| `created_by` | UUID | FK → User, not null |
| `content_hash` | string | SHA-256 over canonical section content |
| `model_id` | string | e.g. `claude-opus-5`; null for `RM_EDITED` |
| `template_version` | string | not null |
| `prompt_version` | string | not null |
| `ledger_id` | UUID | FK → EvidenceLedger, nullable |
| `created_at` | timestamptz | not null |

**Rules**

- Rows are insert-only. A "change" is always a new version.
- `content_hash` is what the RM approves and what export must reproduce (R12).

---

## 8. DocumentSection

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `version_id` | UUID | FK → DocumentVersion, not null |
| `section_key` | string | matches `DocumentTemplate.section_definitions[].key` |
| `ordinal` | int | not null |
| `content` | text | nullable — null when the section is entirely a gap |
| `evidence_refs` | JSONB | array of `claim_id`; **every one must resolve** |
| `gaps` | JSONB | array of `{field, label, resolved, resolution_note}` |
| `confidence` | enum | `HIGH` \| `MEDIUM` \| `LOW` |
| `is_rm_edited` | bool | default false (FR-022) |
| `contains_external_data` | bool | default false (FR-014) |

**Rules**

- **Validation invariant**: every `claim_id` in `evidence_refs` must exist in the version's
  ledger. An unresolvable reference means unsourced content — the section is rejected and
  converted to a gap (R3, FR-011).
- **Numeric invariant**: every numeric literal in `content` must appear in a referenced claim.
  A number with no evidence is a fabrication and fails the generation closed (SC-004).
- `confidence = LOW` MUST be rendered with a visual flag (FR-012).
- A section may have both `content` and `gaps` — partial grounding is normal and honest.

---

## 9. EvidenceLedger & EvidenceClaim

The bottleneck of the grounding architecture (R3). Pass B can only cite what Pass A recorded.

### EvidenceLedger

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `document_id` | UUID | FK → Document, not null |
| `built_at` | timestamptz | not null |
| `model_id` | string | model that produced the grounding pass |
| `source_manifest` | JSONB | every source offered, and whether the RM included it (FR-004) |

### EvidenceClaim

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `ledger_id` | UUID | FK → EvidenceLedger, not null |
| `claim_id` | string | stable within the ledger; referenced by sections |
| `claim_text` | text | not null — the normalised factual statement |
| `source_type` | enum | `CLIENT_RECORD` \| `UPLOADED_DOCUMENT` \| `MEETING_NOTES` |
| `source_id` | UUID | FK → ClientRecord \| SourceDocument, nullable for notes |
| `locator` | JSONB | `{page_start, page_end}` or `{char_start, char_end}` |
| `verbatim_excerpt` | text | not null — the exact cited span |
| `is_external` | bool | default false |

**Rules**

- `verbatim_excerpt` is captured from the provider's native citation (`cited_text`), never
  paraphrased. It is what the RM sees when they inspect a source (FR-024).
- Claims are immutable once written.
- A ledger with zero claims is a valid outcome — it produces an all-gaps document, which is the
  correct behaviour for a client with no records (spec edge case).

---

## 10. ScreeningResult

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `version_id` | UUID | FK → DocumentVersion, not null |
| `layer` | enum | `DETERMINISTIC` \| `SEMANTIC` |
| `outcome` | enum | `PASS` \| `BLOCKED` \| `FLAGGED` |
| `findings` | JSONB | array of `{term, section_key, offset, severity, rule_id}` |
| `vocabulary_version` | string | not null |
| `screened_at` | timestamptz | not null |

**Rules**

- A `DETERMINISTIC` result of `BLOCKED` prevents display of the version (FR-016). It is the
  binding gate.
- A `SEMANTIC` result may be `FLAGGED` but **never** `PASS`-clears a deterministic block
  (R5) — the semantic layer can only add findings.
- Screening runs before the draft is shown, on every version.

---

## 11. ApprovalRecord

The immutable evidence that a named human took responsibility.

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `document_id` | UUID | FK → Document, **unique** (one approval per document) |
| `version_id` | UUID | FK → DocumentVersion, not null |
| `approved_by` | UUID | FK → User, not null |
| `approver_name` | string | not null — **denormalised snapshot** |
| `approver_role` | string | not null — snapshot; must be `RM` |
| `content_hash` | string | not null; must equal the approved version's hash |
| `shariah_status_at_approval` | enum | not null |
| `gaps_acknowledged` | JSONB | any gaps the RM explicitly accepted |
| `approved_at` | timestamptz | not null |

**Rules**

- Insert-only. There is no un-approve; a superseding document is created instead.
- `approver_name` and `approver_role` are snapshotted deliberately. If the user record is later
  changed or deactivated, the audit record must still show who approved and in what capacity
  (Principle VIII).
- `content_hash` binds the approval to exact content. Approving version 3 does not approve
  version 4.

---

## 12. AuditEvent

Append-only, hash-chained, immutable at the database privilege level (R6).

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `sequence` | bigserial | monotonic; chain order |
| `event_type` | enum | `GENERATION_STARTED` \| `GENERATION_COMPLETED` \| `GENERATION_FAILED` \| `SECTION_EDITED` \| `SECTION_REGENERATED` \| `SCREENING_BLOCKED` \| `DOCUMENT_REJECTED` \| `DOCUMENT_APPROVED` \| `DOCUMENT_EXPORTED` \| `SOURCE_UPLOADED` \| `AUDIT_EXPORTED` |
| `occurred_at` | timestamptz | not null |
| `actor_id` | UUID | FK → User, nullable (null for system events) |
| `client_reference` | string | nullable |
| `document_id` | UUID | nullable |
| `version_id` | UUID | nullable |
| `document_type` | string | nullable |
| `input_source_ids` | JSONB | every source used |
| `model_id` | string | nullable |
| `model_version` | string | nullable |
| `prompt_version` | string | nullable |
| `template_version` | string | nullable |
| `output_hash` | string | nullable |
| `detail` | JSONB | event-specific payload — **never document content** |
| `prev_hash` | string | SHA-256 of the previous row's `event_hash` |
| `event_hash` | string | `SHA256(prev_hash ‖ canonical_json(payload))` |

**Rules**

- Application role holds `INSERT, SELECT` only. `UPDATE` and `DELETE` are not granted
  (FR-032). This is enforced by privilege, not by code.
- `detail` never contains document content, client-bearing prompt text, or credentials
  (NFR-SEC-04, FR-042). It carries identifiers and counts.
- The chain is verifiable end-to-end; a `GET /audit/verify` endpoint recomputes it.
- Every FR-030 field is present on `GENERATION_COMPLETED` events.

---

## 13. Vocabulary

The reviewable Shariah artifact (R5, FR-019). Stored as a versioned YAML file under source
control and loaded into memory; represented here because screening results reference its
version.

| Field | Type |
|-------|------|
| `version` | string (semver) |
| `approved_structures` | list — Murabaha, Ijara, Wakala, Musharaka, Mudaraba, Salam, Istisna'a |
| `approved_terminology` | map: concept → permitted phrasing |
| `prohibited_terms` | list of `{term, severity, rule_id, rationale}` |
| `prohibited_sectors` | list |

**Rules**

- Plain YAML by design, so a Shariah stakeholder can review it without reading code.
- Every `ScreeningResult` records the `vocabulary_version` applied, so a past screening
  decision is reproducible.

---

## Validation Rules Summary

| Rule | Enforced at | Requirement |
|------|-------------|-------------|
| Every `evidence_ref` resolves to a real claim | Service (post-Pass-B) | FR-011 |
| Every numeric literal traces to a claim | Service (post-Pass-B) | SC-004 |
| Every required section present or gap-marked | Service (post-Pass-B) | FR-009 |
| Approval blocked on unresolved gaps | Service (state machine) | FR-025 |
| Approval restricted to owning RM | Auth dependency + service | FR-026, R11 |
| No time-based or default approval path exists | Absence of any such code path | FR-027 |
| Deterministic screening blocks display | Service (pre-display) | FR-015, FR-016 |
| Shariah status defaults to `PENDING_REVIEW` | Column default | FR-018 |
| Audit rows never updated or deleted | **DB privilege** | FR-032 |
| Audit chain integrity | Verification endpoint | FR-031 |
| Uploads within size and page limits | Pre-upload validation | Edge case |
| All client data synthetic | **DB CHECK constraint** | FR-041 |
| Concurrent edits do not silently overwrite | Optimistic concurrency on `version_number` | FR-040 |
| Logs carry identifiers, never content | Structured logging filter | FR-042 |
