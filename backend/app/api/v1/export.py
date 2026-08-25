"""Export endpoint (task T099).

Only `APPROVED` documents export. A draft has no approved content to distribute, and
exporting one would produce a bank document carrying no accountable human — the exact
outcome Constitution Principle III exists to prevent.

Exporting is itself an audit event: knowing that a document left the system, and when,
is part of the record (FR-036).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.documents import load_document
from app.audit.recorder import AuditRecorder
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db import get_db
from app.documents.models import ApprovalRecord
from app.enums import DocumentStatus
from app.export.docx_renderer import render_docx

router = APIRouter(tags=["Export"])

_MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


@router.get("/documents/{document_id}/export")
def export_document(
    document_id: uuid.UUID,
    export_format: str = Query(default="docx", alias="format", pattern="^(docx|pdf)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Export an approved document with its approval record attached."""
    document, client, version = load_document(document_id, user, db)

    if document.status is not DocumentStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "NOT_APPROVED",
                "message": (
                    "This document has not been approved yet. Review and approve it "
                    "before exporting."
                ),
            },
        )

    approval = db.execute(
        select(ApprovalRecord).where(ApprovalRecord.document_id == document.id)
    ).scalar_one_or_none()

    if export_format == "pdf":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "code": "PDF_NOT_AVAILABLE",
                "message": "PDF export is not available yet. Please export as Word (.docx).",
            },
        )

    content = render_docx(
        document,
        version,
        client_name=client.legal_name,
        client_reference=client.client_reference,
        approval=approval,
    )

    AuditRecorder(db).document_exported(
        actor_id=user.id,
        actor_name=user.full_name,
        client_reference=client.client_reference,
        document_id=document.id,
        version_id=version.id,
        document_type=document.document_type.value,
        output_hash=version.content_hash,
        detail={"format": export_format, "size_bytes": len(content)},
    )
    db.commit()

    filename = (
        f"{client.client_reference}_{document.document_type.value.lower()}"
        f"_v{version.version_number}.docx"
    )

    return Response(
        content=content,
        media_type=_MEDIA_TYPES[export_format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
