"""Evidence Ledger models (data-model.md §9).

The ledger is the bottleneck of the grounding architecture (research.md R3). The
Composition Pass sees only these claims — never the raw sources — so it cannot cite
anything that was not actually extracted from a document with a real locator.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.enums import ClaimSourceType


class EvidenceLedger(Base):
    """The set of grounded claims available to a document's Composition Pass."""

    __tablename__ = "evidence_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document.id"), nullable=False, index=True
    )
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Every source offered to the RM and whether they included it (FR-004).
    source_manifest: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    claims: Mapped[list[EvidenceClaim]] = relationship(back_populates="ledger")

    def claim_ids(self) -> set[str]:
        """The set of claim ids a section is permitted to reference."""
        return {c.claim_id for c in self.claims}


class EvidenceClaim(Base):
    """A single grounded factual claim with its verbatim source span.

    `verbatim_excerpt` is captured from the provider's native citation (`cited_text`)
    and is never paraphrased. It is exactly what the RM sees when they inspect a
    citation (FR-024) — a paraphrased excerpt would defeat the point of showing it.
    """

    __tablename__ = "evidence_claim"
    __table_args__ = (UniqueConstraint("ledger_id", "claim_id", name="uq_claim_ledger_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ledger_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("evidence_ledger.id"), nullable=False, index=True
    )
    claim_id: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[ClaimSourceType] = mapped_column(
        Enum(ClaimSourceType, name="claim_source_type", native_enum=False), nullable=False
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    source_label: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    locator: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    verbatim_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    is_external: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    ledger: Mapped[EvidenceLedger] = relationship(back_populates="claims")

    @property
    def searchable_text(self) -> str:
        """Text searched when tracing a numeric literal back to evidence.

        Both the normalised claim and the verbatim excerpt count: a figure may appear
        formatted differently in the model's phrasing than in the source document.
        """
        return f"{self.claim_text}\n{self.verbatim_excerpt}"
