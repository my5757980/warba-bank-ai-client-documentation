<!--
SYNC IMPACT REPORT
==================
Version change: TEMPLATE (unversioned) → 1.0.0
Bump rationale: Initial ratification of a complete constitution. All placeholder
tokens replaced with concrete, binding principles for Warba Bank Corporate
Banking AI Challenge — Track 1 (AI-Powered Client Documentation).

Modified principles:
  [PRINCIPLE_1_NAME] → I. Banking-Grade Security & Compliance (NON-NEGOTIABLE)
  [PRINCIPLE_2_NAME] → II. Shariah-Governance Readiness (NON-NEGOTIABLE)
  [PRINCIPLE_3_NAME] → III. Human-in-the-Loop: The RM Decides (NON-NEGOTIABLE)
  [PRINCIPLE_4_NAME] → IV. Accuracy Over Speed
  [PRINCIPLE_5_NAME] → V. Simple, Fast Experience for Relationship Managers
  [PRINCIPLE_6_NAME] → VI. Modular & Scalable Architecture
  (new)              → VII. No Real Client Data (NON-NEGOTIABLE)
  (new)              → VIII. Total Auditability

Added sections:
  - Security, Compliance & Data Constraints (was [SECTION_2_NAME])
  - Development Workflow & Quality Gates (was [SECTION_3_NAME])
  - Governance (populated)

Removed sections: none

Templates requiring updates:
  ✅ .specify/templates/plan-template.md — "Constitution Check" gate is
     constitution-driven by design; no edit required. Plans MUST enumerate the
     eight gates named in Governance → Compliance review.
  ✅ .specify/templates/spec-template.md — structure compatible; specs MUST add
     Shariah-impact and data-classification notes under Requirements.
  ✅ .specify/templates/tasks-template.md — structure compatible; task lists MUST
     include audit-logging and RM-approval tasks for any generation feature.
  ✅ .claude/commands/*.md — no outdated or agent-specific references found.
  ⚠ README.md / docs/quickstart.md — do not yet exist; create with a link to this
     constitution when the repository is scaffolded.

Deferred items:
  - TODO(GOVERNANCE_BODY): Name the accountable reviewers (Compliance, Shariah
    Board liaison, Engineering owner) once the challenge team roster is fixed.
-->

# Warba Bank AI-Powered Client Documentation Constitution

This constitution governs Track 1 of the Warba Bank Corporate Banking AI Challenge:
an AI system that drafts corporate client documentation for Relationship Managers (RMs).
Its principles are non-negotiable. Where this document conflicts with convenience,
deadlines, or demo polish, this document wins.

## Core Principles

### I. Banking-Grade Security & Compliance (NON-NEGOTIABLE)

The system MUST be built as if it were already running inside a regulated bank.

- All data MUST be encrypted in transit (TLS 1.2+) and at rest.
- Access MUST be authenticated and role-based; an RM sees only their own portfolio.
- Secrets, API keys, and model credentials MUST live in environment configuration or a
  secret manager. A hardcoded credential is a build-blocking defect.
- No client-identifying content MAY be sent to any third-party service that is not
  explicitly approved and documented in the plan.
- The system MUST be designed for alignment with CBK regulations, AML/KYC obligations,
  and data-residency expectations. Any deviation MUST be recorded as a known gap.

**Rationale**: A banking prototype that cannot survive a security review is not a
prototype — it is rework.

### II. Shariah-Governance Readiness (NON-NEGOTIABLE)

Warba Bank is an Islamic bank. The system MUST never produce or imply non-compliant terms.

- Generated documents MUST use Islamic finance terminology and structures
  (e.g., Murabaha, Ijara, Wakala) and MUST NOT reference interest (riba), conventional
  loans, or prohibited sectors.
- Every generated document MUST carry a Shariah-review status field that defaults to
  `PENDING_REVIEW`.
- Product terminology MUST come from a configurable, reviewable vocabulary source — never
  from free-form model invention.
- Content that cannot be mapped to an approved Islamic product MUST be flagged, not guessed.

**Rationale**: Shariah compliance is a licence condition, not a feature toggle.

### III. Human-in-the-Loop: The RM Decides (NON-NEGOTIABLE)

The AI drafts. The Relationship Manager approves. Always.

- No document MAY be finalised, sent, filed, or acted upon without explicit RM approval.
- Every AI output MUST be presented as an editable draft, clearly labelled as AI-generated.
- Approval MUST be a deliberate, recorded event — never a default, a timeout, or a silent
  auto-accept.
- The RM MUST be able to edit, reject, or regenerate any section without losing prior
  versions.

**Rationale**: Accountability cannot be delegated to a model. A named human owns every
document that leaves the bank.

### IV. Accuracy Over Speed

A slow correct answer beats a fast invented one. Hallucination is the primary risk.

- Every factual claim in a generated document MUST be traceable to a supplied source
  (client record, uploaded file, or approved template). Unsourced generation is prohibited.
- Missing information MUST be rendered as an explicit gap marker (e.g.
  `[MISSING: annual turnover]`) — never inferred, estimated, or filled with plausible text.
- Outputs MUST expose citations or source references for each generated section.
- Low-confidence sections MUST be visually flagged for RM attention.
- An accuracy regression MUST block release even when latency targets are met.

**Rationale**: One fabricated figure in a credit memo destroys trust in the entire system.

### V. Simple, Fast Experience for Relationship Managers

The system MUST be usable by a busy RM with no training and no manual.

- The core journey — select client → generate → review → approve → export — MUST be
  completable in five interactions or fewer.
- Perceived response time MUST stay under 3 seconds for interactive actions; longer
  generation MUST stream or show honest progress, never a frozen screen.
- The interface MUST use plain banking language, not model or system jargon.
- Any feature that increases RM cognitive load without a measured benefit MUST be removed.

**Rationale**: Adoption is the real success metric. An unused tool has zero value.

### VI. Modular & Scalable Architecture

The prototype MUST be the first increment of a real system, not a throwaway demo.

- Layers MUST be separated — data access, retrieval, prompt/generation, validation,
  presentation — and each MUST be independently testable.
- The LLM provider MUST sit behind an abstraction so it can be swapped or self-hosted
  without touching business logic.
- Document types MUST be added through configuration and templates, not code forks.
- Prompts, templates, and vocabularies MUST be versioned artifacts stored in the repository.
- A new document type MUST be addable without modifying the generation engine.

**Rationale**: The challenge is a pilot. The architecture MUST survive the pilot.

### VII. No Real Client Data (NON-NEGOTIABLE)

The prototype MUST operate exclusively on synthetic, anonymised, or dummy data.

- No real customer name, civil or national ID, account number, contact detail, or financial
  statement MAY enter the repository, any environment, any log, or any demo.
- All sample data MUST be clearly marked as fictitious and stored under a dedicated
  fixtures path.
- Any accidental introduction of real data MUST trigger immediate removal, history purge,
  and disclosure to the challenge sponsor.
- Automated checks SHOULD scan commits for patterns resembling real identifiers.

**Rationale**: A data incident during a competition is still a data incident.

### VIII. Total Auditability

Every generated document MUST be reconstructable and explainable after the fact.

- Each generation event MUST record: timestamp, actor (RM ID), client reference, document
  type, input sources, model and version, prompt/template version, and output hash.
- Every edit, regeneration, rejection, and approval MUST be appended to an immutable audit
  trail. Audit records MUST NOT be editable or deletable by application users.
- Document versions MUST be retained; an approved document MUST be linked to the exact
  inputs and prompt version that produced it.
- Audit records MUST be exportable for compliance review in a machine-readable format.

**Rationale**: If the bank cannot explain how a document was produced, it cannot defend it.

## Security, Compliance & Data Constraints

- **Data classification**: All data handled by the system is treated as Confidential by
  default, even when synthetic.
- **Logging**: Logs MUST be structured and MUST NOT contain document content, prompts
  carrying client data, or credentials. Log identifiers, not payloads.
- **Retention**: Audit trails are append-only for the life of the project. Working drafts
  MAY expire; approval records MAY NOT.
- **Third-party services**: Every external dependency and model endpoint MUST be listed in
  the plan with its data-handling posture before first use.
- **Failure posture**: On any validation, retrieval, or model failure the system MUST fail
  closed — surface the error to the RM and produce no document — rather than emit partial
  or unverified content.
- **Prompt injection**: Content ingested from uploaded documents MUST be treated as
  untrusted data, never as instructions.

## Development Workflow & Quality Gates

- **Spec-Driven Development**: Every feature follows spec → plan → tasks → implementation.
  No implementation begins without an approved spec.
- **Constitution Check**: Every `plan.md` MUST include an explicit pass/fail check against
  all eight principles. Violations MUST be justified in Complexity Tracking, or the plan is
  rejected.
- **Smallest viable diff**: Changes MUST be small, reviewable, and scoped to the task.
  Unrelated refactoring is out of scope.
- **Testing discipline**: Generation, validation, and audit paths MUST have automated tests.
  Grounding and hallucination checks MUST be part of the test suite.
- **Traceability**: Every user prompt MUST produce a Prompt History Record under
  `history/prompts/`. Every significant architectural decision MUST be offered as an ADR
  under `history/adr/`.
- **Definition of Done**: Acceptance criteria met, tests passing, no real data present, no
  hardcoded secrets, audit events emitted, RM approval path intact, PHR written.

## Governance

This constitution supersedes all other practices, conventions, and preferences in this
project. It binds every contributor, human or AI.

- **Authority**: Any code, prompt, document, or design that violates a NON-NEGOTIABLE
  principle (I, II, III, VII) MUST NOT be merged, demonstrated, or delivered.
- **Amendment procedure**: An amendment requires (a) a written rationale, (b) a version
  bump in this file, (c) an updated Sync Impact Report above, and (d) a consistency review
  of all dependent templates. Amendments MUST NOT be made silently during unrelated work.
- **Versioning policy**: Semantic versioning.
  - MAJOR — a principle is removed or redefined in a backward-incompatible way.
  - MINOR — a principle or governance section is added or materially expanded.
  - PATCH — clarification, wording, or typo fixes that do not change meaning.
- **Compliance review**: Every plan and every pull request MUST be verified against all
  eight principles. Reviewers MUST reject work that cannot demonstrate grounding,
  auditability, an intact RM approval path, and the absence of real data.
- **Runtime guidance**: `CLAUDE.md` provides day-to-day agent development guidance and is
  subordinate to this constitution.
- **Accountability**: TODO(GOVERNANCE_BODY): Record the accountable Compliance reviewer,
  Shariah Board liaison, and Engineering owner once the challenge team roster is confirmed.

**Version**: 1.0.0 | **Ratified**: 2026-08-21 | **Last Amended**: 2026-08-21
