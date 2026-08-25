"""API request and response schemas, mirroring contracts/openapi.yaml."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.clients.context_assembler import AssembledContext
from app.documents.generation_service import GenerationOutcome
from app.documents.models import Document, DocumentVersion
from app.evidence.models import EvidenceClaim

# --------------------------------------------------------------------- clients


class ClientSummary(BaseModel):
    id: uuid.UUID
    client_reference: str
    legal_name: str
    trade_name: str | None = None
    sector: str
    relationship_since: str | None = None
    kyc_status: str
    is_synthetic: Literal[True] = True


class SourceOption(BaseModel):
    source_id: str
    source_type: str
    source_system: str | None = None
    label: str
    effective_date: str | None = None
    is_external: bool = False


class SourceConflictOut(BaseModel):
    field: str
    values: list[dict]


class AssembledContextOut(BaseModel):
    client_id: uuid.UUID
    client_reference: str
    document_type: str
    required_inputs: list[str]
    sources: list[SourceOption]
    conflicts: list[SourceConflictOut]

    @classmethod
    def from_context(cls, ctx: AssembledContext) -> AssembledContextOut:
        return cls(
            client_id=ctx.client_id,
            client_reference=ctx.client_reference,
            document_type=ctx.document_type.value,
            required_inputs=ctx.required_inputs,
            sources=[SourceOption(**vars(s)) for s in ctx.sources],
            conflicts=[SourceConflictOut(field=c.field, values=c.values) for c in ctx.conflicts],
        )


# ------------------------------------------------------------------- documents


class GenerateRequest(BaseModel):
    client_id: uuid.UUID
    document_type: str
    meeting_notes: str | None = Field(
        default=None,
        description="Required for CALL_REPORT. Treated as untrusted data, never instruction.",
    )
    source_document_ids: list[uuid.UUID] = Field(default_factory=list)
    client_record_ids: list[uuid.UUID] = Field(default_factory=list)
    rm_instruction: str | None = Field(
        default=None,
        max_length=1000,
        description=(
            "Optional stylistic steer. Scoped to presentation only — it cannot "
            "authorise a claim, alter screening, or affect approval."
        ),
    )


class GapOut(BaseModel):
    field: str
    label: str
    resolved: bool = False
    resolution_note: str | None = None


class SectionOut(BaseModel):
    section_key: str
    title: str
    ordinal: int
    content: str | None
    evidence_refs: list[str]
    gaps: list[GapOut]
    confidence: str
    is_rm_edited: bool
    contains_external_data: bool


class ScreeningOut(BaseModel):
    outcome: str
    vocabulary_version: str
    findings: list[dict]


class DocumentDetail(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_reference: str
    document_type: str
    status: str
    shariah_status: str
    created_by: uuid.UUID
    created_at: datetime
    version_number: int
    content_hash: str
    # Always true. AI-generated content is labelled at all times (FR-020).
    ai_generated: Literal[True] = True
    template_version: str
    prompt_version: str
    model_id: str | None
    sections: list[SectionOut]
    unresolved_gap_count: int
    screening: ScreeningOut | None = None

    @classmethod
    def build(
        cls,
        document: Document,
        version: DocumentVersion,
        client_reference: str,
        screening: ScreeningOut | None = None,
    ) -> DocumentDetail:
        return cls(
            id=document.id,
            client_id=document.client_id,
            client_reference=client_reference,
            document_type=document.document_type.value,
            status=document.status.value,
            shariah_status=document.shariah_status.value,
            created_by=document.created_by,
            created_at=document.created_at,
            version_number=version.version_number,
            content_hash=version.content_hash,
            template_version=version.template_version,
            prompt_version=version.prompt_version,
            model_id=version.model_id,
            sections=[
                SectionOut(
                    section_key=s.section_key,
                    title=s.title,
                    ordinal=s.ordinal,
                    content=s.content,
                    evidence_refs=list(s.evidence_refs or []),
                    gaps=[GapOut(**g) for g in (s.gaps or [])],
                    confidence=s.confidence.value,
                    is_rm_edited=s.is_rm_edited,
                    contains_external_data=s.contains_external_data,
                )
                for s in version.sections
            ],
            unresolved_gap_count=len(version.unresolved_gaps),
            screening=screening,
        )

    @classmethod
    def from_outcome(cls, outcome: GenerationOutcome, client_reference: str) -> DocumentDetail:
        return cls.build(
            outcome.document,
            outcome.version,
            client_reference,
            ScreeningOut(
                outcome=outcome.screening.outcome.value,
                vocabulary_version=outcome.screening.vocabulary_version,
                findings=outcome.screening.findings,
            ),
        )


class DocumentSummary(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_reference: str
    document_type: str
    status: str
    shariah_status: str
    created_by: uuid.UUID
    created_at: datetime


class EvidenceOut(BaseModel):
    claim_id: str
    claim_text: str
    source_type: str
    source_id: uuid.UUID | None
    source_label: str
    locator: dict
    verbatim_excerpt: str
    is_external: bool

    @classmethod
    def from_claim(cls, claim: EvidenceClaim) -> EvidenceOut:
        return cls(
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            source_type=claim.source_type.value,
            source_id=claim.source_id,
            source_label=claim.source_label,
            locator=claim.locator or {},
            verbatim_excerpt=claim.verbatim_excerpt,
            is_external=claim.is_external,
        )


# ------------------------------------------------------------------- sections


class ResolvedGap(BaseModel):
    field: str
    resolution_note: str


class EditSectionRequest(BaseModel):
    content: str | None = None
    resolved_gaps: list[ResolvedGap] = Field(default_factory=list)


class RegenerateRequest(BaseModel):
    instruction: str | None = Field(default=None, max_length=1000)


# ------------------------------------------------------------------- approval


class AcknowledgedGap(BaseModel):
    section_key: str
    field: str
    note: str


class ApproveRequest(BaseModel):
    content_hash: str = Field(description="Hash of the exact version being approved.")
    confirm_reviewed: Literal[True] = Field(
        description=(
            "Explicit affirmation that the RM has reviewed the content and accepts "
            "authorship. Must be literally true — a deliberate act, not a default."
        )
    )
    acknowledge_gaps: list[AcknowledgedGap] = Field(default_factory=list)


class ApprovalRecordOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    approved_by: uuid.UUID
    approver_name: str
    approver_role: str
    content_hash: str
    shariah_status_at_approval: str
    gaps_acknowledged: list[dict]
    approved_at: datetime


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
