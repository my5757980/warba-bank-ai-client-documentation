"""Append-only audit recorder.

This class deliberately exposes no update or delete method. Combined with the
database privilege in `scripts/create_roles.sql` (INSERT + SELECT only), there is no
route through the application by which an audit record can be altered.

Every write passes through `_payload_guard`, which refuses payloads carrying document
content, prompt text, or credentials. Audit records hold identifiers and counts —
never the material itself (FR-042, NFR-SEC-04).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.audit.chain import compute_event_hash, latest_hash
from app.audit.models import AuditEvent
from app.enums import AuditEventType

# Keys that must never appear in an audit detail payload. Matched case-insensitively
# against the key name, so `Prompt_Text` and `apiKey` are caught alongside the exact
# spellings.
_FORBIDDEN_KEY_PATTERNS = (
    r"content",
    r"prompt",
    r"notes?$",
    r"text$",
    r"body",
    r"excerpt",
    r"secret",
    r"password",
    r"token",
    r"api[_-]?key",
    r"credential",
    r"authorization",
)

_FORBIDDEN_KEY_RE = re.compile("|".join(_FORBIDDEN_KEY_PATTERNS), re.IGNORECASE)

# A long free-text value is document content by another name, whatever it is called.
_MAX_DETAIL_STRING_LENGTH = 200


class AuditPayloadError(ValueError):
    """Raised when a detail payload would leak content into the audit trail."""


def _payload_guard(detail: dict[str, Any], _path: str = "detail") -> None:
    """Reject payloads carrying content, prompt text, or credentials.

    Raises rather than sanitising. Silently stripping a forbidden field would let the
    caller believe it had recorded something it had not, and the fix belongs at the
    call site.
    """
    for key, value in detail.items():
        location = f"{_path}.{key}"

        if _FORBIDDEN_KEY_RE.search(key):
            raise AuditPayloadError(
                f"Audit detail key {location!r} looks like content or a credential. "
                "Audit records carry identifiers and counts, not material "
                "(FR-042, NFR-SEC-04)."
            )

        if isinstance(value, dict):
            _payload_guard(value, location)
        elif isinstance(value, str) and len(value) > _MAX_DETAIL_STRING_LENGTH:
            raise AuditPayloadError(
                f"Audit detail value at {location!r} is {len(value)} characters. "
                f"Values over {_MAX_DETAIL_STRING_LENGTH} are treated as content. "
                "Record an identifier or a hash instead."
            )
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    _payload_guard(item, f"{location}[{index}]")
                elif isinstance(item, str) and len(item) > _MAX_DETAIL_STRING_LENGTH:
                    raise AuditPayloadError(
                        f"Audit detail value at {location}[{index}] is too long to be "
                        "an identifier."
                    )


class AuditRecorder:
    """Writes audit events. Appends only.

    There is no `update`, no `delete`, and no method that accepts an existing event id.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def record(
        self,
        event_type: AuditEventType,
        *,
        actor_id: uuid.UUID | None = None,
        actor_name: str | None = None,
        client_reference: str | None = None,
        document_id: uuid.UUID | None = None,
        version_id: uuid.UUID | None = None,
        document_type: str | None = None,
        input_source_ids: list[str] | None = None,
        model_id: str | None = None,
        model_version: str | None = None,
        prompt_version: str | None = None,
        template_version: str | None = None,
        output_hash: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Append one event, linking it into the hash chain.

        The row is written **once, complete**. An earlier version inserted the event and
        then UPDATEd it to set the hash — which the database correctly refused, because
        `warba_app` holds INSERT and SELECT only. The append-only design caught its own
        implementation, which is the strongest argument for enforcing it at the
        privilege level rather than in code.

        Consequently `occurred_at` is set in Python rather than by a server default: the
        timestamp is part of the hashed payload, so it must exist before the hash is
        computed, and therefore before the INSERT.

        Flushed but not committed, so the event participates in the caller's
        transaction — a generation and its audit record commit together or not at all.
        """
        payload_detail = detail or {}
        _payload_guard(payload_detail)

        prev = latest_hash(self._db)

        event = AuditEvent(
            event_type=event_type,
            occurred_at=datetime.now(UTC),
            actor_id=actor_id,
            actor_name=actor_name,
            client_reference=client_reference,
            document_id=document_id,
            version_id=version_id,
            document_type=document_type,
            input_source_ids=input_source_ids or [],
            model_id=model_id,
            model_version=model_version,
            prompt_version=prompt_version,
            template_version=template_version,
            output_hash=output_hash,
            detail=payload_detail,
            prev_hash=prev,
            event_hash="",  # set below, before the row is ever written
        )

        # Hash first, insert once. Never insert-then-update: UPDATE on audit_event is
        # not granted, and must not be.
        event.event_hash = compute_event_hash(prev, event.chain_payload())

        self._db.add(event)
        self._db.flush()

        return event

    # --- Typed convenience methods -----------------------------------------
    # One per event type so call sites cannot mistype an event name, and so the
    # required fields for each event are visible in the signature.

    def generation_started(self, **kw: Any) -> AuditEvent:
        return self.record(AuditEventType.GENERATION_STARTED, **kw)

    def generation_completed(self, **kw: Any) -> AuditEvent:
        return self.record(AuditEventType.GENERATION_COMPLETED, **kw)

    def generation_failed(self, **kw: Any) -> AuditEvent:
        return self.record(AuditEventType.GENERATION_FAILED, **kw)

    def section_edited(self, **kw: Any) -> AuditEvent:
        return self.record(AuditEventType.SECTION_EDITED, **kw)

    def section_regenerated(self, **kw: Any) -> AuditEvent:
        return self.record(AuditEventType.SECTION_REGENERATED, **kw)

    def screening_blocked(self, **kw: Any) -> AuditEvent:
        return self.record(AuditEventType.SCREENING_BLOCKED, **kw)

    def document_rejected(self, **kw: Any) -> AuditEvent:
        return self.record(AuditEventType.DOCUMENT_REJECTED, **kw)

    def document_approved(self, **kw: Any) -> AuditEvent:
        return self.record(AuditEventType.DOCUMENT_APPROVED, **kw)

    def document_exported(self, **kw: Any) -> AuditEvent:
        return self.record(AuditEventType.DOCUMENT_EXPORTED, **kw)

    def source_uploaded(self, **kw: Any) -> AuditEvent:
        return self.record(AuditEventType.SOURCE_UPLOADED, **kw)

    def audit_exported(self, **kw: Any) -> AuditEvent:
        return self.record(AuditEventType.AUDIT_EXPORTED, **kw)
