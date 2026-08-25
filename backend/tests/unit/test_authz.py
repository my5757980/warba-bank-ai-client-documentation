"""Authorisation rules (task T036).

The rule that matters most: **approval authority belongs to the owning RM alone.**
Every other role — including Compliance, which can read every document in the bank —
is refused. Constitution Principle III places accountability on a named human who owns
the relationship, and an authority that can be exercised by an administrator is not
that.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.auth.dependencies import require_approver, visible_client_or_404
from app.enums import UserRole


class FakeUser:
    def __init__(self, role: UserRole, team_id: uuid.UUID | None = None, active: bool = True):
        self.id = uuid.uuid4()
        self.role = role
        self.team_id = team_id
        self.is_active = active
        self.full_name = "Test User"


class FakeClient:
    def __init__(self, owning_rm_id: uuid.UUID):
        self.id = uuid.uuid4()
        self.owning_rm_id = owning_rm_id


class FakeDb:
    """Minimal session stub returning objects by id."""

    def __init__(self, objects: dict):
        self._objects = objects

    def get(self, _model, obj_id):
        return self._objects.get(obj_id)


class TestPortfolioVisibility:
    def test_rm_sees_own_client(self):
        rm = FakeUser(UserRole.RM)
        client = FakeClient(owning_rm_id=rm.id)
        db = FakeDb({client.id: client})

        assert visible_client_or_404(client.id, rm, db) is client  # type: ignore[arg-type]

    def test_rm_cannot_see_another_rms_client(self):
        rm, other = FakeUser(UserRole.RM), FakeUser(UserRole.RM)
        client = FakeClient(owning_rm_id=other.id)
        db = FakeDb({client.id: client})

        with pytest.raises(HTTPException) as exc:
            visible_client_or_404(client.id, rm, db)  # type: ignore[arg-type]
        assert exc.value.status_code == 404

    def test_out_of_portfolio_returns_404_not_403(self):
        """404, deliberately.

        A 403 would confirm the client exists but belongs to someone else, which is
        itself a small disclosure about another RM's book.
        """
        rm, other = FakeUser(UserRole.RM), FakeUser(UserRole.RM)
        client = FakeClient(owning_rm_id=other.id)
        db = FakeDb({client.id: client})

        with pytest.raises(HTTPException) as exc:
            visible_client_or_404(client.id, rm, db)  # type: ignore[arg-type]

        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "NOT_FOUND"

    def test_team_lead_sees_own_team(self):
        team = uuid.uuid4()
        lead = FakeUser(UserRole.TEAM_LEAD, team_id=team)
        rm = FakeUser(UserRole.RM, team_id=team)
        client = FakeClient(owning_rm_id=rm.id)
        db = FakeDb({client.id: client, rm.id: rm})

        assert visible_client_or_404(client.id, lead, db) is client  # type: ignore[arg-type]

    def test_team_lead_cannot_see_another_team(self):
        lead = FakeUser(UserRole.TEAM_LEAD, team_id=uuid.uuid4())
        rm = FakeUser(UserRole.RM, team_id=uuid.uuid4())
        client = FakeClient(owning_rm_id=rm.id)
        db = FakeDb({client.id: client, rm.id: rm})

        with pytest.raises(HTTPException):
            visible_client_or_404(client.id, lead, db)  # type: ignore[arg-type]

    @pytest.mark.parametrize("role", [UserRole.COMPLIANCE, UserRole.SHARIAH_REVIEWER])
    def test_oversight_roles_read_across_the_book(self, role: UserRole):
        overseer = FakeUser(role)
        client = FakeClient(owning_rm_id=uuid.uuid4())
        db = FakeDb({client.id: client})

        assert visible_client_or_404(client.id, overseer, db) is client  # type: ignore[arg-type]


class TestApprovalAuthority:
    def test_owning_rm_is_admitted(self):
        rm = FakeUser(UserRole.RM)
        client = FakeClient(owning_rm_id=rm.id)
        db = FakeDb({client.id: client})

        actor, admitted = require_approver(client.id, rm, db)  # type: ignore[arg-type]
        assert actor is rm
        assert admitted is client

    @pytest.mark.parametrize(
        "role", [UserRole.TEAM_LEAD, UserRole.COMPLIANCE, UserRole.SHARIAH_REVIEWER]
    )
    def test_every_non_rm_role_is_refused(self, role: UserRole):
        actor = FakeUser(role)
        client = FakeClient(owning_rm_id=actor.id)
        db = FakeDb({client.id: client})

        with pytest.raises(HTTPException) as exc:
            require_approver(client.id, actor, db)  # type: ignore[arg-type]

        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "NOT_AN_RM"

    def test_compliance_can_read_but_cannot_approve(self):
        """The clearest statement of the rule.

        Compliance has the broadest read access in the system and no approval
        authority whatsoever. Read access and approval authority are orthogonal.
        """
        officer = FakeUser(UserRole.COMPLIANCE)
        client = FakeClient(owning_rm_id=uuid.uuid4())
        db = FakeDb({client.id: client})

        assert visible_client_or_404(client.id, officer, db) is client  # type: ignore[arg-type]

        with pytest.raises(HTTPException):
            require_approver(client.id, officer, db)  # type: ignore[arg-type]

    def test_rm_refused_for_client_outside_portfolio(self):
        rm, other = FakeUser(UserRole.RM), FakeUser(UserRole.RM)
        client = FakeClient(owning_rm_id=other.id)
        db = FakeDb({client.id: client})

        with pytest.raises(HTTPException) as exc:
            require_approver(client.id, rm, db)  # type: ignore[arg-type]

        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "NOT_PORTFOLIO_OWNER"

    def test_missing_client_is_refused(self):
        rm = FakeUser(UserRole.RM)
        with pytest.raises(HTTPException):
            require_approver(uuid.uuid4(), rm, FakeDb({}))  # type: ignore[arg-type]
