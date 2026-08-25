"""Deterministic, client-scoped context assembly (research.md R4).

There is no embedding model here, no vector store, and no similarity search — by
decision, not by omission.

Every generation is scoped to exactly one client, so the retrieval question is "load
this client's records", which is a `WHERE client_id = ?`. Semantic retrieval would
insert a probabilistic step *upstream* of grounding, and a chunk retrieval failed to
surface becomes an invisible gap: the model would not know the fact exists, so it could
not mark it missing. Deterministic assembly also makes FR-003 and FR-004 meaningful —
the RM can only review and deselect a candidate set that is knowable in advance.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.models import Client, ClientRecord, SourceDocument
from app.enums import DocumentType, RecordType
from app.ports.types import Source

# Sort floor for records with no effective date, so an undated record never wins a
# recency comparison against a dated one.
_EPOCH = date(1900, 1, 1)

# Which record types each document type actually needs. Loading everything for every
# document would fill the ledger with claims nothing cites.
_RELEVANT_RECORDS: dict[DocumentType, tuple[RecordType, ...]] = {
    DocumentType.CALL_REPORT: (
        RecordType.PROFILE,
        RecordType.INTERACTION,
    ),
    DocumentType.CLIENT_PROFILE: (
        RecordType.PROFILE,
        RecordType.FACILITY,
        RecordType.INTERACTION,
        RecordType.FINANCIAL_SUMMARY,
        RecordType.KYC,
    ),
    DocumentType.CREDIT_MEMO_NARRATIVE: (
        RecordType.PROFILE,
        RecordType.FACILITY,
        RecordType.FINANCIAL_SUMMARY,
        RecordType.INTERACTION,
    ),
    DocumentType.KYC_SUMMARY: (
        RecordType.PROFILE,
        RecordType.KYC,
    ),
}

# Fields compared across sources when detecting conflicts. Restricted to values where
# a disagreement is materially misleading in a client document.
_CONFLICT_FIELDS = (
    "annual_turnover",
    "net_profit",
    "employee_count",
    "legal_name",
    "sector",
    "registered_address",
)


@dataclass
class AvailableSource:
    """One source offered to the RM before generation (FR-003)."""

    source_id: str
    source_type: str
    label: str
    source_system: str | None = None
    effective_date: str | None = None
    is_external: bool = False


@dataclass
class SourceConflict:
    """Two sources disagreeing on the same field.

    Surfaced to the RM rather than resolved (FR-013). Silently picking one value would
    hide a data-quality problem the RM is better placed to judge than the system is.
    """

    field: str
    values: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AssembledContext:
    """The complete candidate context for one generation."""

    client_id: uuid.UUID
    client_reference: str
    document_type: DocumentType
    required_inputs: list[str]
    sources: list[AvailableSource] = field(default_factory=list)
    conflicts: list[SourceConflict] = field(default_factory=list)


def assemble_context(
    db: Session,
    client: Client,
    document_type: DocumentType,
    *,
    required_inputs: list[str] | None = None,
) -> AssembledContext:
    """Assemble every source that could ground this document.

    Returns candidates, not a selection. The RM sees this list and chooses what to
    include before anything is generated.
    """
    record_types = _RELEVANT_RECORDS.get(document_type, ())

    records = list(
        db.execute(
            select(ClientRecord)
            .where(
                ClientRecord.client_id == client.id,
                ClientRecord.record_type.in_(record_types),
            )
            .order_by(ClientRecord.effective_date.desc().nullslast())
        ).scalars()
    )

    documents = list(
        db.execute(
            select(SourceDocument)
            .where(SourceDocument.client_id == client.id)
            .order_by(SourceDocument.uploaded_at.desc())
        ).scalars()
    )

    sources = [
        AvailableSource(
            source_id=str(r.id),
            source_type="CLIENT_RECORD",
            label=r.label,
            source_system=r.source_system.value,
            effective_date=r.effective_date.isoformat() if r.effective_date else None,
            is_external=r.is_external,
        )
        for r in records
    ] + [
        AvailableSource(
            source_id=str(d.id),
            source_type="UPLOADED_DOCUMENT",
            label=d.label,
            effective_date=d.uploaded_at.date().isoformat(),
            is_external=False,
        )
        for d in documents
    ]

    return AssembledContext(
        client_id=client.id,
        client_reference=client.client_reference,
        document_type=document_type,
        required_inputs=required_inputs or [],
        sources=sources,
        conflicts=detect_conflicts(records),
    )


def detect_conflicts(records: list[ClientRecord]) -> list[SourceConflict]:
    """Find fields where two records disagree.

    Only the most recent value per source system is compared. Two records from the same
    system at different dates are a history, not a conflict; the same field differing
    between Core Banking and CRM on the same date is a genuine discrepancy.
    """
    latest_by_system: dict[str, ClientRecord] = {}
    for record in records:
        key = record.source_system.value
        current = latest_by_system.get(key)
        if current is None:
            latest_by_system[key] = record
            continue
        if (record.effective_date or _EPOCH) > (current.effective_date or _EPOCH):
            latest_by_system[key] = record

    conflicts: list[SourceConflict] = []

    for field_name in _CONFLICT_FIELDS:
        seen: dict[str, list[dict[str, Any]]] = {}
        for system, record in latest_by_system.items():
            value = record.payload.get(field_name)
            if value is None:
                continue
            seen.setdefault(str(value), []).append(
                {"source_id": str(record.id), "source_system": system, "value": value}
            )

        if len(seen) > 1:
            conflicts.append(
                SourceConflict(
                    field=field_name,
                    values=[entry for group in seen.values() for entry in group],
                )
            )

    return conflicts


def build_sources(
    db: Session,
    client: Client,
    *,
    client_record_ids: list[uuid.UUID],
    source_document_ids: list[uuid.UUID],
    meeting_notes: str | None = None,
) -> list[Source]:
    """Convert the RM's selection into port-level `Source` objects.

    Ids are re-scoped to the client here rather than trusted from the request. A client
    record id from another client would otherwise ground this document in someone
    else's data — a portfolio leak arriving through the body rather than the path.
    """
    sources: list[Source] = []

    if client_record_ids:
        records = db.execute(
            select(ClientRecord).where(
                ClientRecord.id.in_(client_record_ids),
                ClientRecord.client_id == client.id,
            )
        ).scalars()

        for record in records:
            sources.append(
                Source(
                    source_id=str(record.id),
                    kind="CLIENT_RECORD",
                    label=record.label,
                    content=_render_record(record),
                    is_external=record.is_external,
                )
            )

    if source_document_ids:
        documents = db.execute(
            select(SourceDocument).where(
                SourceDocument.id.in_(source_document_ids),
                SourceDocument.client_id == client.id,
            )
        ).scalars()

        for document in documents:
            sources.append(
                Source(
                    source_id=str(document.id),
                    kind="UPLOADED_DOCUMENT",
                    label=document.label,
                    provider_file_id=document.provider_file_id,
                    media_type=document.media_type,
                )
            )

    if meeting_notes and meeting_notes.strip():
        sources.append(
            Source(
                source_id="meeting_notes",
                kind="MEETING_NOTES",
                label="Meeting notes (RM supplied)",
                content=meeting_notes.strip(),
            )
        )

    return sources


def _render_record(record: ClientRecord) -> str:
    """Render a structured record as readable text for the Grounding Pass.

    Rendered as labelled lines rather than raw JSON: the extraction pass produces
    better citation spans over prose-like text than over punctuation-heavy JSON.
    """
    lines = [f"{record.label} (effective {record.effective_date or 'undated'})"]
    for key, value in sorted(record.payload.items()):
        label = key.replace("_", " ").title()
        lines.append(f"{label}: {value}")
    return "\n".join(lines)
