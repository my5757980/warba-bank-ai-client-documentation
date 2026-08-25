"""Domain enumerations shared across the application.

Two of these encode constitutional guarantees in the type system rather than in
prose, and are commented accordingly: `TrustLevel` and `ShariahStatus`.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Application roles.

    Only `RM` may approve a document, and only for a client in their own portfolio.
    Accountability under Constitution Principle III belongs to the named human who
    owns the relationship — it cannot be delegated upward to a team lead or an
    administrator, so no other role is ever granted approval.
    """

    RM = "RM"
    TEAM_LEAD = "TEAM_LEAD"
    COMPLIANCE = "COMPLIANCE"
    SHARIAH_REVIEWER = "SHARIAH_REVIEWER"


class KycStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"


class RecordType(StrEnum):
    PROFILE = "PROFILE"
    FACILITY = "FACILITY"
    INTERACTION = "INTERACTION"
    FINANCIAL_SUMMARY = "FINANCIAL_SUMMARY"
    KYC = "KYC"


class SourceSystem(StrEnum):
    CORE_BANKING = "CORE_BANKING"
    CRM = "CRM"
    KYC_SYSTEM = "KYC_SYSTEM"
    PRODUCT_CATALOGUE = "PRODUCT_CATALOGUE"
    EXTERNAL_REGISTRY = "EXTERNAL_REGISTRY"


class TrustLevel(StrEnum):
    """Trust classification for ingested content.

    Single-valued by design. Uploaded documents and pasted notes are data, never
    instruction (FR-007, research.md R7). A field that *could* be set to `TRUSTED`
    is a field someone eventually sets, so the alternative simply does not exist.
    """

    UNTRUSTED = "UNTRUSTED"


class DocumentType(StrEnum):
    CALL_REPORT = "CALL_REPORT"
    CLIENT_PROFILE = "CLIENT_PROFILE"
    CREDIT_MEMO_NARRATIVE = "CREDIT_MEMO_NARRATIVE"
    KYC_SUMMARY = "KYC_SUMMARY"


class DocumentStatus(StrEnum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"


class ShariahStatus(StrEnum):
    """Shariah review status of a document.

    Always starts at `PENDING_REVIEW`. The system never sets `CLEARED` — it prepares
    documents for Shariah review, it does not clear them (Constitution Principle II).
    There is deliberately no code path in this application that assigns `CLEARED`.
    """

    PENDING_REVIEW = "PENDING_REVIEW"
    CLEARED = "CLEARED"
    FLAGGED = "FLAGGED"


class VersionOrigin(StrEnum):
    GENERATED = "GENERATED"
    REGENERATED_SECTION = "REGENERATED_SECTION"
    RM_EDITED = "RM_EDITED"


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ClaimSourceType(StrEnum):
    CLIENT_RECORD = "CLIENT_RECORD"
    UPLOADED_DOCUMENT = "UPLOADED_DOCUMENT"
    MEETING_NOTES = "MEETING_NOTES"


class ScreeningLayer(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    SEMANTIC = "SEMANTIC"


class ScreeningOutcome(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    FLAGGED = "FLAGGED"


class AuditEventType(StrEnum):
    GENERATION_STARTED = "GENERATION_STARTED"
    GENERATION_COMPLETED = "GENERATION_COMPLETED"
    GENERATION_FAILED = "GENERATION_FAILED"
    SECTION_EDITED = "SECTION_EDITED"
    SECTION_REGENERATED = "SECTION_REGENERATED"
    SCREENING_BLOCKED = "SCREENING_BLOCKED"
    DOCUMENT_REJECTED = "DOCUMENT_REJECTED"
    DOCUMENT_APPROVED = "DOCUMENT_APPROVED"
    DOCUMENT_EXPORTED = "DOCUMENT_EXPORTED"
    SOURCE_UPLOADED = "SOURCE_UPLOADED"
    AUDIT_EXPORTED = "AUDIT_EXPORTED"
