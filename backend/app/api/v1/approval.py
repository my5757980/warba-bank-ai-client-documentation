"""The approval endpoint (task T097).

**This is the only route in the API that can move a document to APPROVED.**

Constitution Principle III is enforced twice on purpose:

  1. `require_approver` refuses anyone who is not the owning RM, producing a clean 403
     at the edge.
  2. `state_machine.approve` re-checks role, ownership, confirmation, content hash,
     gaps, and screening.

The duplication is deliberate. The dependency gives a good error message; the state
machine guarantees the rule holds even if some future caller bypasses the dependency.
For a NON-NEGOTIABLE principle, one layer of enforcement is one fewer than it deserves.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.documents import load_document
from app.api.v1.schemas import ApprovalRecordOut, ApproveRequest
from app.audit.recorder import AuditRecorder
from app.auth.dependencies import get_current_user, require_approver
from app.auth.models import User
from app.db import get_db
from app.documents.models import ApprovalRecord
from app.documents.state_machine import ApprovalRequest, approve
from app.enums import ScreeningOutcome
from app.screening.models import ScreeningResult

router = APIRouter(tags=["Approval"])


@router.post("/documents/{document_id}/approve", response_model=ApprovalRecordOut)
def approve_document(
    document_id: uuid.UUID,
    payload: ApproveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApprovalRecordOut:
    """Approve a document. The only path into APPROVED.

    There is no timeout, no default, no bulk action, and no administrative override.
    A document reaches APPROVED because a named Relationship Manager who owns the
    client relationship deliberately said so, having seen the exact content they are
    approving.
    """
    document, client, version = load_document(document_id, user, db)

    # Edge-level authority check. Raises 403 for any non-RM, and for an RM who does not
    # own this client's portfolio.
    actor, _ = require_approver(client.id, user, db)

    screening = db.execute(
        select(ScreeningResult)
        .where(
            ScreeningResult.version_id == version.id,
            ScreeningResult.layer == "DETERMINISTIC",
        )
        .order_by(ScreeningResult.screened_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    # State machine check. Re-verifies everything above plus content hash, gaps, and
    # confirmation, and is the only code in the system that assigns APPROVED.
    approve(
        document,
        version,
        ApprovalRequest(
            actor=actor,
            content_hash=payload.content_hash,
            confirm_reviewed=payload.confirm_reviewed,
            acknowledged_gaps=[g.model_dump() for g in payload.acknowledge_gaps],
        ),
        owning_rm_id=client.owning_rm_id,
        screening_outcome=screening.outcome if screening else ScreeningOutcome.PASS,
    )

    record = ApprovalRecord(
        document_id=document.id,
        version_id=version.id,
        approved_by=actor.id,
        # Snapshotted so the record survives later changes to the user row: if the RM
        # is renamed, reassigned, or deactivated, the file must still show who approved
        # and in what capacity (Principle VIII).
        approver_name=actor.full_name,
        approver_role=actor.role.value,
        content_hash=version.content_hash,
        shariah_status_at_approval=document.shariah_status,
        gaps_acknowledged=[g.model_dump() for g in payload.acknowledge_gaps],
    )
    db.add(record)
    db.flush()

    AuditRecorder(db).document_approved(
        actor_id=actor.id,
        actor_name=actor.full_name,
        client_reference=client.client_reference,
        document_id=document.id,
        version_id=version.id,
        document_type=document.document_type.value,
        model_id=version.model_id,
        prompt_version=version.prompt_version,
        template_version=version.template_version,
        output_hash=version.content_hash,
        detail={
            "approver_role": actor.role.value,
            "gaps_acknowledged": len(payload.acknowledge_gaps),
            "version": version.version_number,
            "shariah_status": document.shariah_status.value,
        },
    )
    db.commit()

    return ApprovalRecordOut(
        id=record.id,
        document_id=record.document_id,
        version_id=record.version_id,
        approved_by=record.approved_by,
        approver_name=record.approver_name,
        approver_role=record.approver_role,
        content_hash=record.content_hash,
        shariah_status_at_approval=record.shariah_status_at_approval.value,
        gaps_acknowledged=record.gaps_acknowledged,
        approved_at=record.approved_at,
    )
