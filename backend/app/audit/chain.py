"""Audit hash chain (research.md R6).

Each event stores the SHA-256 of the previous event's hash together with its own
canonical payload. Altering any historical row breaks every link from that row
forward, and verification names the exact break point.

This is what turns the audit trail from tamper-*discouraged* into tamper-*evident*.
The database privilege in `scripts/create_roles.sql` stops the application from
rewriting history; the chain detects anyone who bypasses the application.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditEvent

# The hash of the notional event before the first one. A fixed, documented constant
# so the chain has a deterministic anchor rather than a NULL special case.
GENESIS_HASH = "0" * 64


def canonical_json(payload: dict[str, Any]) -> str:
    """Serialise a payload so its hash is reproducible.

    Sorted keys and fixed separators. Without both, two logically identical payloads
    can serialise differently and produce different hashes, which would make the chain
    unverifiable for reasons that have nothing to do with tampering.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def compute_event_hash(prev_hash: str | None, payload: dict[str, Any]) -> str:
    """Compute `SHA256(prev_hash ‖ canonical_json(payload))`."""
    anchor = prev_hash or GENESIS_HASH
    material = f"{anchor}{canonical_json(payload)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def content_hash(payload: dict[str, Any]) -> str:
    """Hash arbitrary content (used for document version hashes)."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def latest_hash(db: Session) -> str | None:
    """The `event_hash` of the most recent event, or None on an empty chain."""
    stmt = select(AuditEvent.event_hash).order_by(AuditEvent.sequence.desc()).limit(1)
    return db.execute(stmt).scalar_one_or_none()


@dataclass(frozen=True)
class ChainVerification:
    """Result of verifying the chain end to end."""

    valid: bool
    events_checked: int
    first_broken_sequence: int | None = None
    reason: str | None = None


def verify_chain(db: Session, document_id: Any = None) -> ChainVerification:
    """Recompute the chain and report the first break, if any.

    Verification always walks from the true beginning of the chain even when scoped to
    one document, because a `prev_hash` links to the globally previous event, not to
    the previous event for that document. Scoping only narrows what is *reported*.
    """
    stmt = select(AuditEvent).order_by(AuditEvent.sequence.asc())
    events = list(db.execute(stmt).scalars())

    if not events:
        return ChainVerification(valid=True, events_checked=0)

    expected_prev: str = GENESIS_HASH

    for event in events:
        stored_prev = event.prev_hash or GENESIS_HASH

        if stored_prev != expected_prev:
            return ChainVerification(
                valid=False,
                events_checked=len(events),
                first_broken_sequence=event.sequence,
                reason="prev_hash does not match the preceding event's hash",
            )

        recomputed = compute_event_hash(stored_prev, event.chain_payload())
        if recomputed != event.event_hash:
            return ChainVerification(
                valid=False,
                events_checked=len(events),
                first_broken_sequence=event.sequence,
                reason="event content does not match its stored hash",
            )

        expected_prev = event.event_hash

    if document_id is not None:
        # Scoped report: the chain is globally intact, which is what a per-document
        # view needs to assert.
        relevant = [e for e in events if e.document_id == document_id]
        return ChainVerification(valid=True, events_checked=len(relevant))

    return ChainVerification(valid=True, events_checked=len(events))
