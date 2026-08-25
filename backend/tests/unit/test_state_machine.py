"""Document state machine (task T064).

Constitution Principle III lives here. These tests assert every approval precondition
independently, and — most importantly — that no path into APPROVED exists other than an
explicit human request that satisfies all of them.
"""

from __future__ import annotations

import uuid

import pytest

from app.documents.state_machine import (
    ApprovalRequest,
    TransitionError,
    approve,
    can_edit,
    reject,
    transition_to_draft,
)
from app.enums import DocumentStatus, ScreeningOutcome, UserRole


class FakeUser:
    def __init__(self, role: UserRole = UserRole.RM, is_active: bool = True):
        self.id = uuid.uuid4()
        self.role = role
        self.is_active = is_active
        self.full_name = "Test User"


class FakeVersion:
    def __init__(self, content_hash: str = "hash-v1", gaps: list[dict] | None = None):
        self.id = uuid.uuid4()
        self.content_hash = content_hash
        self._gaps = gaps or []

    @property
    def unresolved_gaps(self) -> list[dict]:
        return self._gaps


class FakeDocument:
    def __init__(self, status: DocumentStatus = DocumentStatus.DRAFT):
        self.id = uuid.uuid4()
        self.status = status
        self.current_version_id = None


def request_for(
    user: FakeUser,
    *,
    content_hash: str = "hash-v1",
    confirm: bool = True,
    acknowledged: list[dict] | None = None,
) -> ApprovalRequest:
    return ApprovalRequest(
        actor=user,  # type: ignore[arg-type]
        content_hash=content_hash,
        confirm_reviewed=confirm,
        acknowledged_gaps=acknowledged or [],
    )


def approve_with(document, version, request, owner_id=None, screening=ScreeningOutcome.PASS):
    approve(
        document,  # type: ignore[arg-type]
        version,  # type: ignore[arg-type]
        request,
        owning_rm_id=owner_id if owner_id is not None else request.actor.id,
        screening_outcome=screening,
    )


class TestHappyPath:
    def test_owning_rm_can_approve_a_clean_document(self):
        rm = FakeUser()
        doc, version = FakeDocument(), FakeVersion()
        approve_with(doc, version, request_for(rm))
        assert doc.status is DocumentStatus.APPROVED

    def test_acknowledged_gap_permits_approval(self):
        """Acknowledging is a deliberate acceptance, not a bypass — it is recorded."""
        rm = FakeUser()
        version = FakeVersion(gaps=[{"section_key": "financials", "field": "turnover"}])
        doc = FakeDocument()
        approve_with(
            doc,
            version,
            request_for(rm, acknowledged=[{"section_key": "financials", "field": "turnover"}]),
        )
        assert doc.status is DocumentStatus.APPROVED


class TestRoleRestriction:
    @pytest.mark.parametrize(
        "role", [UserRole.TEAM_LEAD, UserRole.COMPLIANCE, UserRole.SHARIAH_REVIEWER]
    )
    def test_non_rm_roles_cannot_approve(self, role: UserRole):
        """Accountability cannot be delegated upward or sideways."""
        actor = FakeUser(role=role)
        doc, version = FakeDocument(), FakeVersion()
        with pytest.raises(TransitionError) as exc:
            approve_with(doc, version, request_for(actor))
        assert exc.value.code == "NOT_AN_RM"
        assert doc.status is DocumentStatus.DRAFT

    def test_inactive_rm_cannot_approve(self):
        actor = FakeUser(is_active=False)
        doc, version = FakeDocument(), FakeVersion()
        with pytest.raises(TransitionError) as exc:
            approve_with(doc, version, request_for(actor))
        assert exc.value.code == "INACTIVE_ACTOR"


class TestPortfolioOwnership:
    def test_rm_cannot_approve_another_rms_client(self):
        rm, other_rm = FakeUser(), FakeUser()
        doc, version = FakeDocument(), FakeVersion()
        with pytest.raises(TransitionError) as exc:
            approve_with(doc, version, request_for(rm), owner_id=other_rm.id)
        assert exc.value.code == "NOT_PORTFOLIO_OWNER"
        assert doc.status is DocumentStatus.DRAFT


class TestDeliberateAct:
    def test_confirmation_must_be_explicitly_true(self):
        rm = FakeUser()
        doc, version = FakeDocument(), FakeVersion()
        with pytest.raises(TransitionError) as exc:
            approve_with(doc, version, request_for(rm, confirm=False))
        assert exc.value.code == "NOT_CONFIRMED"

    def test_truthy_is_not_enough(self):
        """`confirm_reviewed` is checked with `is not True`, not truthiness.

        A string, a 1, or any other truthy value is a caller mistake, not consent.
        """
        rm = FakeUser()
        doc, version = FakeDocument(), FakeVersion()
        req = ApprovalRequest(
            actor=rm,  # type: ignore[arg-type]
            content_hash="hash-v1",
            confirm_reviewed="yes",  # type: ignore[arg-type]
            acknowledged_gaps=[],
        )
        with pytest.raises(TransitionError) as exc:
            approve_with(doc, version, req)
        assert exc.value.code == "NOT_CONFIRMED"


class TestVersionBinding:
    def test_stale_content_hash_is_refused(self):
        """Approving version 3 must not approve version 4."""
        rm = FakeUser()
        doc, version = FakeDocument(), FakeVersion(content_hash="hash-v2")
        with pytest.raises(TransitionError) as exc:
            approve_with(doc, version, request_for(rm, content_hash="hash-v1"))
        assert exc.value.code == "STALE_CONTENT_HASH"
        assert doc.status is DocumentStatus.DRAFT


class TestGapBlocking:
    def test_unresolved_gap_blocks_approval(self):
        rm = FakeUser()
        version = FakeVersion(gaps=[{"section_key": "financials", "field": "turnover"}])
        doc = FakeDocument()
        with pytest.raises(TransitionError) as exc:
            approve_with(doc, version, request_for(rm))
        assert exc.value.code == "UNRESOLVED_GAPS"
        assert exc.value.detail["unresolved_gaps"][0]["field"] == "turnover"

    def test_partially_acknowledged_gaps_still_block(self):
        rm = FakeUser()
        version = FakeVersion(
            gaps=[
                {"section_key": "financials", "field": "turnover"},
                {"section_key": "financials", "field": "net_profit"},
            ]
        )
        doc = FakeDocument()
        with pytest.raises(TransitionError) as exc:
            approve_with(
                doc,
                version,
                request_for(rm, acknowledged=[{"section_key": "financials", "field": "turnover"}]),
            )
        assert exc.value.code == "UNRESOLVED_GAPS"
        assert len(exc.value.detail["unresolved_gaps"]) == 1


class TestScreeningGate:
    def test_blocked_screening_prevents_approval(self):
        rm = FakeUser()
        doc, version = FakeDocument(), FakeVersion()
        with pytest.raises(TransitionError) as exc:
            approve_with(doc, version, request_for(rm), screening=ScreeningOutcome.BLOCKED)
        assert exc.value.code == "SCREENING_BLOCKED"


class TestTerminality:
    def test_approved_document_cannot_be_reapproved(self):
        rm = FakeUser()
        doc = FakeDocument(status=DocumentStatus.APPROVED)
        with pytest.raises(TransitionError) as exc:
            approve_with(doc, FakeVersion(), request_for(rm))
        assert exc.value.code == "ALREADY_APPROVED"

    def test_approved_document_cannot_be_edited(self):
        with pytest.raises(TransitionError):
            can_edit(FakeDocument(status=DocumentStatus.APPROVED))  # type: ignore[arg-type]

    def test_approved_document_cannot_be_rejected(self):
        with pytest.raises(TransitionError):
            reject(FakeDocument(status=DocumentStatus.APPROVED))  # type: ignore[arg-type]

    def test_draft_can_be_rejected(self):
        doc = FakeDocument()
        reject(doc)  # type: ignore[arg-type]
        assert doc.status is DocumentStatus.REJECTED


class TestNoImplicitApprovalPath:
    def test_module_exposes_no_other_route_to_approved(self):
        """The strongest assertion in this file.

        `approve()` is the only public function in the module that can assign
        `APPROVED`. If someone later adds a convenience helper — an auto-approve, a
        bulk-approve, a scheduled finaliser — this test fails and the reviewer is
        forced to justify it against Principle III.
        """
        import inspect
        import re

        from app.documents import state_machine

        # Match the assignment specifically. A guard clause that *reads* APPROVED
        # (`if document.status is DocumentStatus.APPROVED`) is exactly what we want
        # functions to have — it is a refusal, not a route.
        assigns_approved = re.compile(r"status\s*=\s*DocumentStatus\.APPROVED")

        setters = []
        for name, obj in inspect.getmembers(state_machine, inspect.isfunction):
            if obj.__module__ != state_machine.__name__:
                continue
            if assigns_approved.search(inspect.getsource(obj)):
                setters.append(name)

        assert setters == ["approve"], (
            f"Expected only `approve` to assign APPROVED status; found {setters}. "
            "Any new path into APPROVED must be justified against Principle III."
        )

    def test_transition_to_draft_never_yields_approved(self):
        doc, version = FakeDocument(), FakeVersion()
        transition_to_draft(doc, version)  # type: ignore[arg-type]
        assert doc.status is DocumentStatus.DRAFT
