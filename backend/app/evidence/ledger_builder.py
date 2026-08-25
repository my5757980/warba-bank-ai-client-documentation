"""Evidence ledger persistence (task T054).

The port returns an in-memory `Ledger`; this module writes it to the database and reads
it back. The `source_manifest` records every source that was *offered* alongside those
the RM actually included — a manifest that only listed inclusions could not answer the
audit question "what did the RM choose not to use?" (FR-004).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evidence.models import EvidenceClaim, EvidenceLedger
from app.ports.types import Claim, Ledger


def build_source_manifest(
    *,
    offered: list[tuple[str, str]],
    included: list[str],
) -> dict:
    """Record what was offered and what the RM included.

    Args:
        offered: (source_id, label) for every source the assembler surfaced.
        included: source_ids the RM kept.
    """
    included_set = set(included)
    return {
        "offered_count": len(offered),
        "included_count": len(included_set),
        "sources": [
            {"source_id": sid, "label": label, "included": sid in included_set}
            for sid, label in offered
        ],
    }


def persist_ledger(db: Session, document_id: uuid.UUID, ledger: Ledger) -> EvidenceLedger:
    """Write a ledger and its claims.

    Claims are insert-only. A ledger belongs to the generation that produced it, so a
    regeneration reuses the existing ledger rather than rewriting this one — otherwise
    a version's citations could come to point at claims that were not in scope when it
    was written.
    """
    row = EvidenceLedger(
        document_id=document_id,
        model_id=ledger.model_id,
        source_manifest=ledger.source_manifest,
    )
    db.add(row)
    db.flush()

    for claim in ledger.claims:
        db.add(
            EvidenceClaim(
                ledger_id=row.id,
                claim_id=claim.claim_id,
                claim_text=claim.claim_text,
                source_type=claim.source_type,
                source_id=_as_uuid(claim.source_id),
                source_label=claim.source_label,
                locator=claim.locator,
                verbatim_excerpt=claim.verbatim_excerpt,
                is_external=claim.is_external,
            )
        )

    db.flush()
    return row


def load_ledger(db: Session, ledger_id: uuid.UUID) -> Ledger:
    """Read a persisted ledger back into port-level types.

    Used by section regeneration, which must compose against the *same* evidence the
    original generation saw. Re-grounding would let the evidence shift underneath a
    document the RM has already partly accepted.
    """
    row = db.get(EvidenceLedger, ledger_id)
    if row is None:
        return Ledger()

    claims = list(
        db.execute(
            select(EvidenceClaim)
            .where(EvidenceClaim.ledger_id == ledger_id)
            .order_by(EvidenceClaim.claim_id)
        ).scalars()
    )

    return Ledger(
        claims=[
            Claim(
                claim_id=c.claim_id,
                claim_text=c.claim_text,
                source_type=c.source_type.value,
                source_id=str(c.source_id) if c.source_id else None,
                source_label=c.source_label,
                verbatim_excerpt=c.verbatim_excerpt,
                locator=c.locator or {},
                is_external=c.is_external,
            )
            for c in claims
        ],
        model_id=row.model_id,
        source_manifest=row.source_manifest or {},
    )


def _as_uuid(value: str | None) -> uuid.UUID | None:
    """Convert a claim's source id, tolerating non-UUID sentinels.

    Meeting notes use the literal id `"meeting_notes"` rather than a row id, because
    they are supplied per-request and never persisted as a source row.
    """
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None
