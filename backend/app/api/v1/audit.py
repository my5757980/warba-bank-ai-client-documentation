"""Audit endpoints (tasks T152–T155) — US4.

Read-only, by design and by database privilege. There is no create, update, or delete
counterpart anywhere in this API, and the `warba_app` role holds INSERT and SELECT only
on `audit_event` (scripts/create_roles.sql). An audit trail the application can rewrite
proves nothing.

`/audit/verify` is what makes the trail tamper-*evident* rather than merely
tamper-discouraged: it recomputes the hash chain end to end and names the first broken
link. Someone who bypasses the application and edits the table directly still cannot
produce a chain that verifies.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.chain import verify_chain
from app.audit.models import AuditEvent
from app.audit.recorder import AuditRecorder
from app.auth.dependencies import require_role
from app.auth.models import User
from app.db import get_db
from app.documents.models import ApprovalRecord, Document, DocumentVersion
from app.enums import UserRole

router = APIRouter(tags=["Audit"])

# Compliance reads the audit trail. A Team Lead reviewing their team's output has a
# legitimate need too, but neither can write to it — read access and write access are
# separate questions, and only one of them has an answer here.
_AUDIT_READERS = (UserRole.COMPLIANCE, UserRole.TEAM_LEAD)


def _event_dict(event: AuditEvent) -> dict:
    return {
        "id": str(event.id),
        "sequence": event.sequence,
        "event_type": event.event_type.value,
        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "actor_name": event.actor_name,
        "client_reference": event.client_reference,
        "document_id": str(event.document_id) if event.document_id else None,
        "version_id": str(event.version_id) if event.version_id else None,
        "document_type": event.document_type,
        "input_source_ids": event.input_source_ids,
        "model_id": event.model_id,
        "model_version": event.model_version,
        "prompt_version": event.prompt_version,
        "template_version": event.template_version,
        "output_hash": event.output_hash,
        "detail": event.detail,
        "prev_hash": event.prev_hash,
        "event_hash": event.event_hash,
    }


@router.get("/audit/events")
def list_events(
    document_id: uuid.UUID | None = Query(default=None),
    client_reference: str | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_role(*_AUDIT_READERS)),
    db: Session = Depends(get_db),
) -> dict:
    """Query the audit trail (FR-034)."""
    stmt = select(AuditEvent)

    if document_id:
        stmt = stmt.where(AuditEvent.document_id == document_id)
    if client_reference:
        stmt = stmt.where(AuditEvent.client_reference == client_reference)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if from_:
        stmt = stmt.where(AuditEvent.occurred_at >= from_)
    if to:
        stmt = stmt.where(AuditEvent.occurred_at <= to)

    events = db.execute(
        stmt.order_by(AuditEvent.sequence.desc()).limit(limit).offset(offset)
    ).scalars()

    return {"items": [_event_dict(e) for e in events], "total": len(list(events))}


@router.get("/audit/documents/{document_id}/lifecycle")
def document_lifecycle(
    document_id: uuid.UUID,
    user: User = Depends(require_role(*_AUDIT_READERS)),
    db: Session = Depends(get_db),
) -> dict:
    """The full reconstructable history of one document (SC-013).

    Answers "how was this produced" without anyone reading the code: every generation,
    edit, regeneration, rejection, screening block, and approval, in order, with the
    model, template, and prompt versions used at each step.
    """
    document = db.get(Document, document_id)
    if document is None:
        return {"error": "Document not found."}

    versions = list(
        db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number)
        ).scalars()
    )

    events = list(
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.document_id == document_id)
            .order_by(AuditEvent.sequence)
        ).scalars()
    )

    approval = db.execute(
        select(ApprovalRecord).where(ApprovalRecord.document_id == document_id)
    ).scalar_one_or_none()

    chain = verify_chain(db, document_id=document_id)

    return {
        "document": {
            "id": str(document.id),
            "client_id": str(document.client_id),
            "document_type": document.document_type.value,
            "status": document.status.value,
            "shariah_status": document.shariah_status.value,
            "created_at": document.created_at.isoformat(),
        },
        "versions": [
            {
                "id": str(v.id),
                "version_number": v.version_number,
                "origin": v.origin.value,
                "created_by": str(v.created_by),
                "content_hash": v.content_hash,
                "model_id": v.model_id,
                "template_version": v.template_version,
                "prompt_version": v.prompt_version,
                "created_at": v.created_at.isoformat(),
            }
            for v in versions
        ],
        "approval": (
            {
                "approver_name": approval.approver_name,
                "approver_role": approval.approver_role,
                "content_hash": approval.content_hash,
                "shariah_status_at_approval": approval.shariah_status_at_approval.value,
                "gaps_acknowledged": approval.gaps_acknowledged,
                "approved_at": approval.approved_at.isoformat(),
            }
            if approval
            else None
        ),
        "events": [_event_dict(e) for e in events],
        "chain_valid": chain.valid,
    }


@router.get("/audit/export")
def export_audit(
    document_id: uuid.UUID | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    export_format: str = Query(default="json", alias="format", pattern="^(json|csv)$"),
    user: User = Depends(require_role(UserRole.COMPLIANCE)),
    db: Session = Depends(get_db),
) -> Response:
    """Export audit records in a machine-readable format (FR-035).

    The export is itself an audit event. Knowing that the trail was extracted, by whom,
    and when is part of the record.
    """
    stmt = select(AuditEvent)
    if document_id:
        stmt = stmt.where(AuditEvent.document_id == document_id)
    if from_:
        stmt = stmt.where(AuditEvent.occurred_at >= from_)
    if to:
        stmt = stmt.where(AuditEvent.occurred_at <= to)

    events = list(db.execute(stmt.order_by(AuditEvent.sequence)).scalars())
    rows = [_event_dict(e) for e in events]

    AuditRecorder(db).audit_exported(
        actor_id=user.id,
        actor_name=user.full_name,
        document_id=document_id,
        detail={"format": export_format, "record_count": len(rows)},
    )
    db.commit()

    if export_format == "csv":
        buffer = io.StringIO()
        if rows:
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: v for k, v in row.items()})
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="audit_export.csv"'},
        )

    import json

    return Response(
        content=json.dumps(rows, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="audit_export.json"'},
    )


@router.get("/audit/verify")
def verify(
    user: User = Depends(require_role(*_AUDIT_READERS)),
    db: Session = Depends(get_db),
) -> dict:
    """Verify the hash chain end to end.

    A broken link proves tampering and names the first affected sequence number. This is
    the difference between an audit trail you have to trust and one you can check.
    """
    result = verify_chain(db)
    return {
        "valid": result.valid,
        "events_checked": result.events_checked,
        "first_broken_sequence": result.first_broken_sequence,
        "reason": result.reason,
    }
