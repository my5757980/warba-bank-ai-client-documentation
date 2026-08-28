"""Audit query behaviour against a live database.

Covers two defects that only appeared once the trail had rows in it, and that no
pure-logic test could have caught:

  · `total` was computed from an already-drained result and always reported 0, so a
    reviewer paging the trail was told it was empty while looking at its contents.
  · a draft refused by the *input-side* Shariah screen was never recorded, because that
    screen fires in the route handler before the generation service — the only place
    that writes screening audit events — is reached.

Both are about whether a compliance reviewer can see what actually happened, which is
the point of having an audit trail at all.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from app.api.v1.audit import list_events
from app.audit.recorder import AuditRecorder
from app.config import get_settings
from app.db import get_session_factory
from app.enums import UserRole


def _database_available() -> bool:
    try:
        engine = create_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _database_available(),
    reason="No live database. Run: docker compose up -d && alembic upgrade head",
)


class _Reader:
    """Stand-in for the authenticated compliance user.

    `list_events` is called directly rather than through the router, so the `Depends`
    are never evaluated and a plain object suffices.
    """

    id = uuid.uuid4()
    full_name = "Test Reviewer"
    role = UserRole.COMPLIANCE


def _query(session, **filters) -> dict:
    """Call the endpoint function directly, supplying every parameter.

    FastAPI resolves `Query(...)` defaults only while routing. Called as a plain
    function, any argument left out arrives as the `Query` object itself and is handed
    straight to SQLAlchemy — which fails with an enum lookup error rather than anything
    that points at the cause. So every parameter is passed, none defaulted.
    """
    args: dict = {
        "document_id": None,
        "client_reference": None,
        "actor_id": None,
        "event_type": None,
        "from_": None,
        "to": None,
        "limit": 100,
        "offset": 0,
    }
    args.update(filters)
    return list_events(user=_Reader, db=session, **args)


@pytest.fixture
def session():
    with get_session_factory()() as s:
        yield s


def _seed(session, count: int, client_reference: str) -> None:
    recorder = AuditRecorder(session)
    for _ in range(count):
        recorder.screening_blocked(
            actor_id=_Reader.id,
            actor_name=_Reader.full_name,
            client_reference=client_reference,
            document_type="CALL_REPORT",
            detail={"stage": "rm_input", "rule_ids": ["SH-001"], "finding_count": 1},
        )
    session.commit()


class TestTotalIsCounted:
    def test_total_matches_the_number_of_rows(self, session):
        """The regression: `total` must not be 0 while items are being returned."""
        reference = f"TEST-{uuid.uuid4().hex[:8]}"
        _seed(session, 3, reference)

        result = _query(session, client_reference=reference)

        assert len(result["items"]) == 3
        assert result["total"] == 3

    def test_total_counts_all_matches_not_just_the_page(self, session):
        """`total` describes the filter, not the page — that is what makes it useful."""
        reference = f"TEST-{uuid.uuid4().hex[:8]}"
        _seed(session, 5, reference)

        page = _query(session, client_reference=reference, limit=2)

        assert len(page["items"]) == 2
        assert page["total"] == 5

    def test_no_matches_reports_zero(self, session):
        result = _query(session, client_reference="TEST-NOTHING-MATCHES")

        assert result["items"] == []
        assert result["total"] == 0


class TestInputScreenBlockIsRecorded:
    """A refusal on the RM's own input must leave a trace.

    The output-side screen was already audited; this one fires earlier, in the route
    handler, and used to raise without recording anything.
    """

    def test_the_event_is_queryable_with_its_rule_ids(self, session):
        reference = f"TEST-{uuid.uuid4().hex[:8]}"
        _seed(session, 1, reference)

        result = _query(session, client_reference=reference, event_type="SCREENING_BLOCKED")

        assert result["total"] == 1
        event = result["items"][0]
        assert event["detail"]["stage"] == "rm_input"
        assert event["detail"]["rule_ids"] == ["SH-001"]

    def test_the_event_is_chained(self, session):
        """It joins the hash chain like any other event — no unlinked side entries."""
        reference = f"TEST-{uuid.uuid4().hex[:8]}"
        _seed(session, 2, reference)

        items = _query(session, client_reference=reference)["items"]

        assert all(e["event_hash"] for e in items)
        assert all(e["prev_hash"] for e in items)
        assert len({e["sequence"] for e in items}) == 2
