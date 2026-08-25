"""Document lifecycle state machine (data-model.md §6).

**This module is the only writer of `Document.status`.** No other module assigns it, and
there is no scheduler, timer, background job, or default that moves a document toward
`APPROVED`. Constitution Principle III is not a policy statement here — it is the
absence of any code path that could violate it.

Every approval precondition is checked in one place, so a new caller cannot approve a
document by forgetting a check it did not know existed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.auth.models import User
from app.documents.models import Document, DocumentVersion
from app.enums import DocumentStatus, ScreeningOutcome, UserRole


class TransitionError(Exception):
    """Raised when a requested transition is not permitted.

    `code` maps to an HTTP status in the API layer so the RM gets an accurate reason
    rather than a generic refusal.
    """

    def __init__(self, message: str, *, code: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


@dataclass(frozen=True)
class ApprovalRequest:
    """An explicit, deliberate request to approve one specific version.

    `content_hash` and `confirm_reviewed` are both required, and neither has a default.
    An approval that could be constructed without them would be an approval that could
    happen by accident.
    """

    actor: User
    content_hash: str
    confirm_reviewed: bool
    acknowledged_gaps: list[dict]


def can_edit(document: Document) -> None:
    """Raise unless the document is in an editable state."""
    if document.status is DocumentStatus.APPROVED:
        raise TransitionError(
            "This document has been approved and can no longer be edited. "
            "Create a new document if a correction is needed.",
            code="ALREADY_APPROVED",
        )


def transition_to_draft(document: Document, version: DocumentVersion) -> None:
    """Record a new working version. Used after generation, edit, or regeneration."""
    can_edit(document)
    document.current_version_id = version.id
    document.status = DocumentStatus.DRAFT


def transition_to_under_review(document: Document) -> None:
    can_edit(document)
    document.status = DocumentStatus.UNDER_REVIEW


def reject(document: Document) -> None:
    """Reject the current draft. Reversible — the RM may regenerate afterwards."""
    if document.status is DocumentStatus.APPROVED:
        raise TransitionError(
            "An approved document cannot be rejected.",
            code="ALREADY_APPROVED",
        )
    document.status = DocumentStatus.REJECTED


def approve(
    document: Document,
    version: DocumentVersion,
    request: ApprovalRequest,
    *,
    owning_rm_id: uuid.UUID,
    screening_outcome: ScreeningOutcome | None,
) -> None:
    """The only transition into `APPROVED`.

    All six preconditions are checked here, in this order, so the RM receives the most
    fundamental reason first rather than a downstream symptom of it.
    """
    # 1. Terminal state. Approving twice would create a second, conflicting record of
    #    who is accountable.
    if document.status is DocumentStatus.APPROVED:
        raise TransitionError(
            "This document has already been approved.",
            code="ALREADY_APPROVED",
        )

    # 2. Role. Approval authority belongs to the RM alone — not a team lead, not an
    #    administrator. Accountability cannot be delegated upward (Principle III).
    if request.actor.role is not UserRole.RM:
        raise TransitionError(
            "Only a Relationship Manager can approve a document.",
            code="NOT_AN_RM",
            detail={"actor_role": request.actor.role.value},
        )

    if not request.actor.is_active:
        raise TransitionError(
            "This account is not active and cannot approve documents.",
            code="INACTIVE_ACTOR",
        )

    # 3. Ownership. The accountable human is the RM who owns the relationship.
    if owning_rm_id != request.actor.id:
        raise TransitionError(
            "You can only approve documents for clients in your own portfolio.",
            code="NOT_PORTFOLIO_OWNER",
        )

    # 4. Deliberate act. A default-true or absent flag would make approval something
    #    that happens rather than something someone does.
    if request.confirm_reviewed is not True:
        raise TransitionError(
            "Approval requires explicit confirmation that you have reviewed this document.",
            code="NOT_CONFIRMED",
        )

    # 5. Exact version. Approving "the document" would let content change underneath an
    #    approval; the RM approves specific content they actually read.
    if request.content_hash != version.content_hash:
        raise TransitionError(
            "This document changed since you opened it. Reload and review the current "
            "version before approving.",
            code="STALE_CONTENT_HASH",
            detail={"expected": version.content_hash},
        )

    # 6. No unresolved gaps. A gap the RM never saw is a gap they never accepted.
    unresolved = version.unresolved_gaps
    if unresolved:
        acknowledged = {(g["section_key"], g["field"]) for g in request.acknowledged_gaps}
        still_open = [
            gap for gap in unresolved if (gap["section_key"], gap["field"]) not in acknowledged
        ]
        if still_open:
            raise TransitionError(
                "Some information is still marked as missing. Fill it in or acknowledge "
                "each gap before approving.",
                code="UNRESOLVED_GAPS",
                detail={"unresolved_gaps": still_open},
            )

    # 7. Screening. A document that never passed the binding gate must not become an
    #    approved bank document.
    if screening_outcome is ScreeningOutcome.BLOCKED:
        raise TransitionError(
            "This document did not pass Shariah screening and cannot be approved.",
            code="SCREENING_BLOCKED",
        )

    document.status = DocumentStatus.APPROVED
