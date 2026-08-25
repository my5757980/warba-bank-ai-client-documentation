"""Screening result model (data-model.md §10)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import ScreeningLayer, ScreeningOutcome


class ScreeningResult(Base):
    """Outcome of one screening layer against one document version.

    A `DETERMINISTIC` result of `BLOCKED` prevents display of the version — it is the
    binding gate (FR-016). A `SEMANTIC` result may raise `FLAGGED`, but nothing in the
    system lets the semantic layer clear a deterministic block (research.md R5): a
    NON-NEGOTIABLE control cannot rest on a probabilistic check.

    `vocabulary_version` is recorded on every result so a past screening decision stays
    reproducible even after the vocabulary is amended.
    """

    __tablename__ = "screening_result"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("document_version.id"), nullable=False, index=True
    )
    layer: Mapped[ScreeningLayer] = mapped_column(
        Enum(ScreeningLayer, name="screening_layer", native_enum=False), nullable=False
    )
    outcome: Mapped[ScreeningOutcome] = mapped_column(
        Enum(ScreeningOutcome, name="screening_outcome", native_enum=False), nullable=False
    )
    findings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    vocabulary_version: Mapped[str] = mapped_column(String(32), nullable=False)
    screened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def blocks_display(self) -> bool:
        """Only the deterministic layer can block. The semantic layer only advises."""
        return (
            self.layer is ScreeningLayer.DETERMINISTIC and self.outcome is ScreeningOutcome.BLOCKED
        )
