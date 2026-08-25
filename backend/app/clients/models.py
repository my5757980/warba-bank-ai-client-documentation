"""Client, ClientRecord, and SourceDocument models (data-model.md §2–§4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import MAX_UPLOAD_BYTES, MAX_UPLOAD_PAGES
from app.db import Base
from app.enums import KycStatus, RecordType, SourceSystem, TrustLevel


class Client(Base):
    """A corporate banking client.

    Every row is synthetic, and that is enforced by a database CHECK constraint rather
    than by convention. Constitution Principle VII is NON-NEGOTIABLE, and a rule
    enforced only in application code is a rule one missing guard defeats.
    """

    __tablename__ = "client"
    __table_args__ = (
        CheckConstraint(
            "is_synthetic = true",
            name="ck_client_synthetic_only",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_reference: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commercial_registration: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sector: Mapped[str] = mapped_column(String(128), nullable=False)
    incorporation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    relationship_since: Mapped[date | None] = mapped_column(Date, nullable=True)
    owning_rm_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False, index=True
    )
    kyc_status: Mapped[KycStatus] = mapped_column(
        Enum(KycStatus, name="kyc_status", native_enum=False), nullable=False
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    records: Mapped[list[ClientRecord]] = relationship(back_populates="client")
    source_documents: Mapped[list[SourceDocument]] = relationship(back_populates="client")


class ClientRecord(Base):
    """A structured internal-source fixture.

    Polymorphic on `record_type` rather than a table per source, so adding an internal
    source category needs no migration (NFR-SCA-01). Records are never mutated in
    place — a correction is a new row with a later `effective_date`, which keeps the
    audit story intact.
    """

    __tablename__ = "client_record"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("client.id"), nullable=False, index=True
    )
    record_type: Mapped[RecordType] = mapped_column(
        Enum(RecordType, name="record_type", native_enum=False), nullable=False
    )
    source_system: Mapped[SourceSystem] = mapped_column(
        Enum(SourceSystem, name="source_system", native_enum=False), nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_external: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    client: Mapped[Client] = relationship(back_populates="records")

    @property
    def label(self) -> str:
        """Human-readable label shown in the context preview."""
        return f"{self.record_type.value.title().replace('_', ' ')} ({self.source_system.value})"


class SourceDocument(Base):
    """An RM-uploaded file used as a grounding source.

    Size and page limits are checked before upload and again here. An oversized file is
    declined with a clear message — never silently truncated, because a truncated
    statement produces a confidently wrong document.
    """

    __tablename__ = "source_document"
    __table_args__ = (
        CheckConstraint(
            f"size_bytes <= {MAX_UPLOAD_BYTES}",
            name="ck_source_document_size",
        ),
        CheckConstraint(
            f"page_count IS NULL OR page_count <= {MAX_UPLOAD_PAGES}",
            name="ck_source_document_pages",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("client.id"), nullable=False, index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_file_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    trust_level: Mapped[TrustLevel] = mapped_column(
        Enum(TrustLevel, name="trust_level", native_enum=False),
        nullable=False,
        default=TrustLevel.UNTRUSTED,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    client: Mapped[Client] = relationship(back_populates="source_documents")

    @property
    def label(self) -> str:
        return self.title or self.filename
