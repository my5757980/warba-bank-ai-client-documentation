"""Audit privilege enforcement (task T024) — the database-level proof of FR-032.

Every other guarantee in this codebase can be verified without a database: screening is
pure text matching, validators are pure comparison, the state machine is pure logic. This
one cannot. FR-032 is a claim about what a *live PostgreSQL role* is permitted to do, and
the only way to verify a claim about the database is to ask the database.

This test connects as `warba_app` — the exact role the application runs as — and attempts
the two operations Constitution Principle VIII forbids. Success looks like a
`psycopg.errors.InsufficientPrivilege`, not like an application-level check catching the
attempt: the guarantee is that the privilege is not there to begin with.

Requires a running database with `scripts/create_roles.sql` applied
(`docker compose up -d`, then the grants). Skipped automatically otherwise — this is an
integration test against real infrastructure, not a substitute for the unit tests that
cover the same principle in `test_audit_chain.py` and `test_audit_payload_guard.py`.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.config import get_settings


def _app_engine():
    """Engine connected as the application role, exactly as the API runs."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def _database_available() -> bool:
    """Probe for a live database with a short timeout.

    Without an explicit `connect_timeout`, a wrong host or a firewalled port hangs for
    the OS-level TCP timeout — 60+ seconds on Windows — before the skip even fires.
    A test suite's fallback path needs to fail fast, not hang.
    """
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


class TestApplicationRoleCannotRewriteAudit:
    """`warba_app` — the role the API connects as — holds INSERT and SELECT only."""

    def test_delete_is_refused(self):
        engine = _app_engine()
        with engine.connect() as conn, pytest.raises(DBAPIError) as exc:
            conn.execute(text("DELETE FROM audit_event WHERE true"))
            conn.commit()

        assert "permission denied" in str(exc.value).lower()

    def test_update_is_refused(self):
        engine = _app_engine()
        with engine.connect() as conn, pytest.raises(DBAPIError) as exc:
            conn.execute(text("UPDATE audit_event SET detail = '{}'::jsonb"))
            conn.commit()

        assert "permission denied" in str(exc.value).lower()

    def test_truncate_is_refused(self):
        """TRUNCATE bypasses row-level logic entirely — it must be refused too."""
        engine = _app_engine()
        with engine.connect() as conn, pytest.raises(DBAPIError) as exc:
            conn.execute(text("TRUNCATE audit_event"))
            conn.commit()

        assert "permission denied" in str(exc.value).lower()

    def test_insert_and_select_are_permitted(self):
        """The role is not locked out of the table — only out of rewriting history.

        Deliberately rolled back rather than committed. Committing would leave a stray
        row with `prev_hash = NULL` in the middle of a real hash chain — which is not a
        genesis event, so it would fail `verify_chain()` on every later run and
        permanently corrupt the demo database's audit trail. A test proving a write
        capability does not need to keep the write.
        """
        engine = _app_engine()
        marker = f"test-marker-{uuid.uuid4().hex}"

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_event "
                    "(id, sequence, event_type, occurred_at, input_source_ids, detail, "
                    " prev_hash, event_hash) "
                    "VALUES (:id, DEFAULT, 'GENERATION_STARTED', now(), '[]'::jsonb, "
                    " '{}'::jsonb, NULL, :hash)"
                ),
                {"id": str(uuid.uuid4()), "hash": marker},
            )

            count = conn.execute(
                text("SELECT count(*) FROM audit_event WHERE event_hash = :hash"),
                {"hash": marker},
            ).scalar_one()

            assert count == 1  # INSERT succeeded and is visible within the transaction

            conn.rollback()

        # Confirm the rollback actually happened — no trace left in the real table.
        with engine.connect() as conn:
            leaked = conn.execute(
                text("SELECT count(*) FROM audit_event WHERE event_hash = :hash"),
                {"hash": marker},
            ).scalar_one()
        assert leaked == 0


class TestSyntheticDataConstraint:
    """`Client.is_synthetic` carries a CHECK constraint — Principle VII enforced by schema."""

    def test_non_synthetic_client_is_rejected(self):
        """The CHECK constraint fires, in isolation from the foreign key.

        A throwaway user is inserted first, in the same uncommitted transaction, so
        `owning_rm_id` is always valid — otherwise this test's outcome would depend on
        which constraint Postgres happens to evaluate first, rather than proving the
        one guarantee it exists to prove.
        """
        engine = _app_engine()
        owner_id = str(uuid.uuid4())

        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO app_user "
                    "(id, email, full_name, password_hash, role, is_active) "
                    "VALUES (:id, :email, 'Throwaway Test User', 'x', 'RM', true)"
                ),
                {"id": owner_id, "email": f"test-{uuid.uuid4().hex[:8]}@test.invalid"},
            )

            with pytest.raises(DBAPIError) as exc:
                conn.execute(
                    text(
                        "INSERT INTO client "
                        "(id, client_reference, legal_name, sector, owning_rm_id, "
                        " kyc_status, is_synthetic) "
                        "VALUES (:id, :ref, 'Real Client Ltd', 'Trading', :owner, "
                        " 'COMPLETE', false)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "ref": f"NOT-SYNTH-{uuid.uuid4().hex[:8]}",
                        "owner": owner_id,
                    },
                )

            message = str(exc.value).lower()
            assert "ck_client_synthetic_only" in message or "check constraint" in message

            conn.rollback()  # discard the throwaway user too
