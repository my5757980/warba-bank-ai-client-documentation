"""Document domain models (data-model.md §5–§8, §11)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import (
    Confidence,
    DocumentStatus,
    DocumentType,
    ShariahStatus,
    VersionOrigin,
)


class DocumentTemplate(Base):
    """Versioned, configurable definition of a document type.

    This entity is what makes NFR-SCA-01 true: a new document type is a row plus a
    template file plus a schema — not a change to the generation engine. Templates are
    immutable once used; a change creates a new `version` so every approved document
    still links to the exact definition that produced it.
    """

    __tablename__ = "document_template"
    __table_args__ = (
        UniqueConstraint("document_type", "version", name="uq_template_type_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type", native_enum=False), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    section_definitions: Mapped[list] = mapped_column(JSONB, nullable=False)
    required_inputs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    screening_profile: Mapped[str] = mapped_column(String(64), nullable=False, default="standard")
    prompt_template_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def required_section_keys(self) -> list[str]:
        return [s["key"] for s in self.section_definitions if s.get("required", True)]


class Document(Base):
    """A generated document instance.

    Owns the lifecycle state Constitution Principle III governs. `status` is written by
    exactly one module — `app.documents.state_machine` — and there is no timer,
    scheduler, or default path into `APPROVED`.
    """

    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("client.id"), nullable=False, index=True
    )
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type", native_enum=False), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document_template.id"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", native_enum=False),
        nullable=False,
        default=DocumentStatus.DRAFT,
    )
    # Always starts PENDING_REVIEW. Nothing in this application sets CLEARED —
    # the system prepares documents for Shariah review, it does not clear them.
    shariah_status: Mapped[ShariahStatus] = mapped_column(
        Enum(ShariahStatus, name="shariah_status", native_enum=False),
        nullable=False,
        default=ShariahStatus.PENDING_REVIEW,
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    template: Mapped[DocumentTemplate] = relationship()
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", order_by="DocumentVersion.version_number"
    )
    approval: Mapped[ApprovalRecord | None] = relationship(back_populates="document", uselist=False)

    @property
    def is_terminal(self) -> bool:
        """An approved document is never edited. A correction is a new document."""
        return self.status is DocumentStatus.APPROVED


class DocumentVersion(Base):
    """An immutable snapshot.

    Every generation, edit, and regeneration creates one. Rows are insert-only: a
    "change" is always a new version, which is what makes the audit trail able to answer
    "what exactly did the RM approve".
    """

    __tablename__ = "document_version"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_version_document_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[VersionOrigin] = mapped_column(
        Enum(VersionOrigin, name="version_origin", native_enum=False), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    ledger_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="versions")
    sections: Mapped[list[DocumentSection]] = relationship(
        back_populates="version", order_by="DocumentSection.ordinal"
    )

    @property
    def unresolved_gaps(self) -> list[dict]:
        """Every gap across all sections that is not yet resolved or acknowledged."""
        out: list[dict] = []
        for section in self.sections:
            for gap in section.gaps or []:
                if not gap.get("resolved", False):
                    out.append({"section_key": section.section_key, **gap})
        return out


class DocumentSection(Base):
    """A discrete part of a document version.

    Two invariants are enforced in `app.documents.validators` before a section is ever
    persisted or shown: every `claim_id` in `evidence_refs` must resolve to a real claim
    in the version's ledger, and every numeric literal in `content` must appear in a
    referenced claim. A section may legitimately carry both content and gaps — partial
    grounding is normal and honest.
    """

    __tablename__ = "document_section"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document_version.id"), nullable=False, index=True
    )
    section_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    gaps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[Confidence] = mapped_column(
        Enum(Confidence, name="confidence", native_enum=False),
        nullable=False,
        default=Confidence.MEDIUM,
    )
    is_rm_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    contains_external_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    version: Mapped[DocumentVersion] = relationship(back_populates="sections")


class ApprovalRecord(Base):
    """Immutable evidence that a named human took responsibility.

    `approver_name` and `approver_role` are denormalised snapshots on purpose: if the
    user record is later renamed, reassigned, or deactivated, the audit record must
    still show who approved and in what capacity (Constitution Principle VIII).

    `content_hash` binds the approval to exact content. Approving version 3 does not
    approve version 4.
    """

    __tablename__ = "approval_record"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id"), nullable=False, unique=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document_version.id"), nullable=False
    )
    approved_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    approver_name: Mapped[str] = mapped_column(String(255), nullable=False)
    approver_role: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    shariah_status_at_approval: Mapped[ShariahStatus] = mapped_column(
        Enum(ShariahStatus, name="shariah_status", native_enum=False), nullable=False
    )
    gaps_acknowledged: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="approval")
