"""Client and document endpoints (tasks T090–T096)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_generation_port
from app.api.v1.schemas import (
    AssembledContextOut,
    ClientSummary,
    DocumentDetail,
    DocumentSummary,
    EvidenceOut,
    GenerateRequest,
    RejectRequest,
    ScreeningOut,
)
from app.audit.recorder import AuditRecorder
from app.auth.dependencies import get_current_user, visible_client_or_404
from app.auth.models import User
from app.clients.context_assembler import assemble_context, build_sources
from app.clients.models import Client
from app.db import get_db
from app.documents.generation_service import GenerationService
from app.documents.models import Document, DocumentVersion
from app.documents.state_machine import reject as reject_document
from app.documents.templates import active_template, schema_for
from app.enums import DocumentType, UserRole
from app.evidence.models import EvidenceClaim
from app.ports.generation_port import GenerationPort
from app.screening.models import ScreeningResult
from app.screening.service import screen_input

router = APIRouter(tags=["Documents"])


# ----------------------------------------------------------------- clients


@router.get("/clients", response_model=list[ClientSummary])
def list_clients(
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ClientSummary]:
    """List clients visible to the caller.

    An RM sees only their own portfolio. Scoping is applied here in the query rather
    than filtered after the fact, so an out-of-portfolio client never enters the result
    set at all.
    """
    stmt = select(Client)

    if user.role is UserRole.RM:
        stmt = stmt.where(Client.owning_rm_id == user.id)
    elif user.role is UserRole.TEAM_LEAD and user.team_id is not None:
        team_rm_ids = select(User.id).where(User.team_id == user.team_id)
        stmt = stmt.where(Client.owning_rm_id.in_(team_rm_ids))

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(Client.legal_name.ilike(pattern) | Client.client_reference.ilike(pattern))

    clients = db.execute(stmt.order_by(Client.legal_name).limit(limit).offset(offset)).scalars()

    return [
        ClientSummary(
            id=c.id,
            client_reference=c.client_reference,
            legal_name=c.legal_name,
            trade_name=c.trade_name,
            sector=c.sector,
            relationship_since=c.relationship_since.isoformat() if c.relationship_since else None,
            kyc_status=c.kyc_status.value,
        )
        for c in clients
    ]


@router.get("/clients/{client_id}/context", response_model=AssembledContextOut)
def get_context(
    client_id: uuid.UUID,
    document_type: DocumentType = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssembledContextOut:
    """Show the RM what the system knows before it writes anything (FR-003).

    Deterministic — no model call and no similarity search, so the candidate set is
    knowable in advance and the RM's deselection (FR-004) is meaningful.
    """
    client = visible_client_or_404(client_id, user, db)
    template = active_template(db, document_type)

    context = assemble_context(
        db, client, document_type, required_inputs=list(template.required_inputs or [])
    )
    return AssembledContextOut.from_context(context)


# --------------------------------------------------------------- documents


@router.post("/documents", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
def create_document(
    payload: GenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    port: GenerationPort = Depends(get_generation_port),
) -> DocumentDetail:
    """Generate a document draft.

    Fails closed. A validation failure returns 422, a screening block returns 451, and a
    service failure returns 503 — in every case with **no document**. The exception
    handlers in `app.api.errors` do the mapping; nothing here returns partial content.
    """
    client = visible_client_or_404(payload.client_id, user, db)

    if user.role is not UserRole.RM:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN_ROLE",
                "message": "Only a Relationship Manager can generate documents.",
            },
        )

    document_type = DocumentType(payload.document_type)
    template = active_template(db, document_type)

    if (
        "meeting_notes" in (template.required_inputs or [])
        and not (payload.meeting_notes or "").strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "MISSING_REQUIRED_INPUT",
                "message": "Meeting notes are required to produce a call report.",
            },
        )

    # Input-side screen: a non-compliant request is flagged before drafting, rather
    # than drafted as though it were compliant (FR-017).
    if payload.meeting_notes:
        screen = screen_input(payload.meeting_notes)
        if screen.blocked:
            from app.audit.recorder import AuditRecorder
            from app.documents.generation_service import ScreeningBlockedError
            from app.screening.vocabulary import get_vocabulary

            vocabulary_version = get_vocabulary().version

            # Record the refusal before raising.
            #
            # The output-side screen is audited inside GenerationService, but this one
            # fires before that service is ever reached — so without this call, a draft
            # refused on the RM's own input left no trace at all. "Show me every time
            # the system refused a request" is the first question a compliance reviewer
            # asks, and a partial answer is a wrong answer.
            #
            # Committed on its own: the raise below aborts the request, and an audit
            # record that rolls back with the thing it was recording is not an audit
            # record.
            audit = AuditRecorder(db)
            audit.screening_blocked(
                actor_id=user.id,
                actor_name=user.full_name,
                client_reference=client.client_reference,
                document_type=document_type.value,
                detail={
                    "stage": "rm_input",
                    "rule_ids": sorted({f.rule_id for f in screen.findings if f.blocks}),
                    "finding_count": len(screen.findings),
                    "vocabulary_version": vocabulary_version,
                },
            )
            db.commit()

            raise ScreeningBlockedError(screen.findings, vocabulary_version)

    sources = build_sources(
        db,
        client,
        client_record_ids=payload.client_record_ids,
        source_document_ids=payload.source_document_ids,
        meeting_notes=payload.meeting_notes,
    )

    service = GenerationService(db, port)
    outcome = service.generate(
        client=client,
        template=template,
        schema=schema_for(document_type),
        sources=sources,
        actor_id=user.id,
        actor_name=user.full_name,
        rm_instruction=payload.rm_instruction,
    )
    db.commit()

    return DocumentDetail.from_outcome(outcome, client.client_reference)


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(
    client_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentSummary]:
    stmt = select(Document, Client).join(Client, Document.client_id == Client.id)

    if user.role is UserRole.RM:
        stmt = stmt.where(Client.owning_rm_id == user.id)
    if client_id:
        stmt = stmt.where(Document.client_id == client_id)
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)

    rows = db.execute(stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)).all()

    return [
        DocumentSummary(
            id=d.id,
            client_id=d.client_id,
            client_reference=c.client_reference,
            document_type=d.document_type.value,
            status=d.status.value,
            shariah_status=d.shariah_status.value,
            created_by=d.created_by,
            created_at=d.created_at,
        )
        for d, c in rows
    ]


def load_document(
    document_id: uuid.UUID, user: User, db: Session
) -> tuple[Document, Client, DocumentVersion]:
    """Fetch a document the caller may see, with its current version."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Document not found."},
        )

    client = visible_client_or_404(document.client_id, user, db)

    version = (
        db.get(DocumentVersion, document.current_version_id)
        if document.current_version_id
        else None
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NO_VERSION", "message": "This document has no content yet."},
        )

    return document, client, version


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    document, client, version = load_document(document_id, user, db)

    screening = db.execute(
        select(ScreeningResult)
        .where(ScreeningResult.version_id == version.id)
        .order_by(ScreeningResult.screened_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    return DocumentDetail.build(
        document,
        version,
        client.client_reference,
        ScreeningOut(
            outcome=screening.outcome.value,
            vocabulary_version=screening.vocabulary_version,
            findings=screening.findings,
        )
        if screening
        else None,
    )


@router.get("/documents/{document_id}/evidence/{claim_id}", response_model=EvidenceOut)
def get_evidence(
    document_id: uuid.UUID,
    claim_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EvidenceOut:
    """Return the verbatim excerpt behind a citation (FR-024).

    The excerpt is returned exactly as captured from the source. Paraphrasing it would
    defeat the purpose — the RM opens this to check the system's reading against the
    document, and a paraphrase cannot be checked.
    """
    _, _, version = load_document(document_id, user, db)

    claim = db.execute(
        select(EvidenceClaim).where(
            EvidenceClaim.ledger_id == version.ledger_id,
            EvidenceClaim.claim_id == claim_id,
        )
    ).scalar_one_or_none()

    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLAIM_NOT_FOUND", "message": "That citation could not be found."},
        )

    return EvidenceOut.from_claim(claim)


@router.post("/documents/{document_id}/reject", response_model=DocumentDetail)
def reject(
    document_id: uuid.UUID,
    payload: RejectRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    document, client, version = load_document(document_id, user, db)

    reject_document(document)

    AuditRecorder(db).document_rejected(
        actor_id=user.id,
        actor_name=user.full_name,
        client_reference=client.client_reference,
        document_id=document.id,
        version_id=version.id,
        document_type=document.document_type.value,
        detail={"had_reason": payload.reason is not None, "version": version.version_number},
    )
    db.commit()

    return DocumentDetail.build(document, version, client.client_reference)
