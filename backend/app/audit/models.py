"""Audit event model (data-model.md §12).

Append-only and hash-chained. Immutability is enforced at two levels:

  1. This module exposes no update or delete path, and neither does `AuditRecorder`.
  2. The `warba_app` database role holds INSERT and SELECT on this table only —
     UPDATE and DELETE are never granted (scripts/create_roles.sql).

The second is the one that matters. An audit table the application *could* rewrite
proves nothing; a revoked privilege cannot be forgotten by a future contributor.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Identity, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import AuditEventType


class AuditEvent(Base):
    """One immutable record of a lifecycle action.

    Every field required by FR-030 is present so a `GENERATION_COMPLETED` event alone
    answers "how was this produced": inputs, model, model version, prompt version,
    template version, and output hash.
    """

    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Monotonic chain order. The hash chain is verified in this sequence.
    #
    # `Identity()` (not `autoincrement=True`) is required here. On a non-primary-key
    # column, autoincrement is ignored on INSERT and SQLAlchemy sends an explicit NULL,
    # which the NOT NULL constraint rejects — every audit write fails. Identity tells
    # SQLAlchemy the server generates the value, so the column is omitted from the
    # INSERT and the database default fires.
    sequence: Mapped[int] = mapped_column(
        BigInteger, Identity(always=False), nullable=False, unique=True
    )
    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(AuditEventType, name="audit_event_type", native_enum=False), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_reference: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    input_source_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    template_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Identifiers and counts only. Never document content, client-bearing prompt text,
    # or credentials (FR-042, NFR-SEC-04). Enforced by the payload guard in recorder.py.
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    def chain_payload(self) -> dict:
        """The canonical subset that is hashed into the chain.

        Deliberately excludes `id` and `sequence`: those are storage concerns, and
        including a server-assigned value would make the hash unreproducible from the
        event's own content.
        """
        return {
            "event_type": self.event_type.value,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "actor_name": self.actor_name,
            "client_reference": self.client_reference,
            "document_id": str(self.document_id) if self.document_id else None,
            "version_id": str(self.version_id) if self.version_id else None,
            "document_type": self.document_type,
            "input_source_ids": self.input_source_ids,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "template_version": self.template_version,
            "output_hash": self.output_hash,
            "detail": self.detail,
        }
