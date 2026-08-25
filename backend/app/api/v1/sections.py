"""Section edit and regeneration endpoints (tasks T094, T095)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_generation_port
from app.api.v1.documents import load_document
from app.api.v1.schemas import DocumentDetail, EditSectionRequest, RegenerateRequest
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db import get_db
from app.documents.generation_service import GenerationService
from app.documents.templates import schema_for
from app.enums import UserRole
from app.ports.generation_port import GenerationPort

router = APIRouter(tags=["Sections"])


def _require_rm(user: User) -> None:
    if user.role is not UserRole.RM:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN_ROLE",
                "message": "Only a Relationship Manager can edit a document.",
            },
        )


@router.patch("/documents/{document_id}/sections/{section_key}", response_model=DocumentDetail)
def edit_section(
    document_id: uuid.UUID,
    section_key: str,
    payload: EditSectionRequest,
    if_match: str = Header(..., alias="If-Match"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    """Edit a section inline, creating a new `RM_EDITED` version.

    `If-Match` carries the content hash of the version the client read. A stale value
    returns 412 rather than applying the edit on top of changes the RM never saw
    (FR-040). Two tabs open on the same document is an ordinary occurrence, and
    silently losing one of them is not an acceptable outcome for a bank record.
    """
    _require_rm(user)
    document, client, version = load_document(document_id, user, db)

    # No port: an RM edit re-screens and re-versions but composes nothing.
    service = GenerationService(db)
    outcome = service.edit_section(
        document=document,
        version=version,
        section_key=section_key,
        expected_hash=if_match.strip('"'),
        content=payload.content,
        resolved_gaps=[g.model_dump() for g in payload.resolved_gaps],
        actor_id=user.id,
        actor_name=user.full_name,
        client_reference=client.client_reference,
    )
    db.commit()

    return DocumentDetail.from_outcome(outcome, client.client_reference)


@router.post(
    "/documents/{document_id}/sections/{section_key}/regenerate",
    response_model=DocumentDetail,
)
def regenerate_section(
    document_id: uuid.UUID,
    section_key: str,
    payload: RegenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    port: GenerationPort = Depends(get_generation_port),
) -> DocumentDetail:
    """Regenerate one section without discarding accepted work elsewhere (FR-023).

    Composes against the *existing* evidence ledger. Re-grounding would let the
    evidence shift underneath sections the RM has already reviewed and accepted.
    """
    _require_rm(user)
    document, client, version = load_document(document_id, user, db)

    service = GenerationService(db, port)
    outcome = service.regenerate_section(
        document=document,
        version=version,
        section_key=section_key,
        schema=schema_for(document.document_type),
        actor_id=user.id,
        actor_name=user.full_name,
        client_reference=client.client_reference,
        instruction=payload.instruction,
    )
    db.commit()

    return DocumentDetail.from_outcome(outcome, client.client_reference)
