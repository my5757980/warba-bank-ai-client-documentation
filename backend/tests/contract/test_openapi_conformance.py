"""OpenAPI conformance (tasks T080, T081).

Verifies the running application against `specs/001-ai-client-documentation/contracts/
openapi.yaml`. The contract is not decoration: it states three invariants the API must
uphold, and these tests check the implementation actually does.

No database and no model calls — the app object is inspected, not driven.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

CONTRACT_PATH = (
    Path(__file__).resolve().parents[3]
    / "specs"
    / "001-ai-client-documentation"
    / "contracts"
    / "openapi.yaml"
)


@pytest.fixture(scope="module")
def contract() -> dict:
    return yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def live_schema() -> dict:
    from app.main import create_app

    return create_app().openapi()


def _paths(schema: dict) -> set[tuple[str, str]]:
    return {
        (path, method.upper())
        for path, ops in schema.get("paths", {}).items()
        for method in ops
        if method in {"get", "post", "patch", "put", "delete"}
    }


# Endpoints specified but deliberately not yet built. Listed explicitly so an
# unimplemented endpoint is a visible decision rather than a silent omission.
NOT_YET_IMPLEMENTED = {
    ("/clients/{client_id}/sources", "POST"),  # T161 — upload (Phase 8)
    ("/documents/{document_id}/versions", "GET"),  # version history UI
}


class TestPathCoverage:
    def test_every_implemented_path_is_in_the_contract(self, contract, live_schema):
        """The API must not grow endpoints the contract never described."""
        contract_paths = _paths(contract)
        live_paths = {
            (path.replace("/api/v1", ""), method)
            for path, method in _paths(live_schema)
            if path.startswith("/api/v1")
        }

        undocumented = live_paths - contract_paths
        assert not undocumented, (
            f"These endpoints exist but are not in contracts/openapi.yaml: {undocumented}"
        )

    def test_contract_paths_are_implemented_or_explicitly_deferred(self, contract, live_schema):
        contract_paths = _paths(contract)
        live_paths = {
            (path.replace("/api/v1", ""), method)
            for path, method in _paths(live_schema)
            if path.startswith("/api/v1")
        }

        missing = contract_paths - live_paths - NOT_YET_IMPLEMENTED
        assert not missing, f"Contract endpoints not implemented and not deferred: {missing}"

    def test_us1_journey_endpoints_all_exist(self, live_schema):
        """The five-interaction journey must be complete end to end."""
        live = _paths(live_schema)
        for path, method in [
            ("/api/v1/auth/login", "POST"),
            ("/api/v1/clients", "GET"),
            ("/api/v1/clients/{client_id}/context", "GET"),
            ("/api/v1/documents", "POST"),
            ("/api/v1/documents/{document_id}", "GET"),
            ("/api/v1/documents/{document_id}/approve", "POST"),
            ("/api/v1/documents/{document_id}/export", "GET"),
        ]:
            assert (path, method) in live, f"{method} {path} is missing"


class TestApprovalContract:
    """The approval endpoint carries Constitution Principle III."""

    def test_approve_is_the_only_route_mentioning_approval(self, live_schema):
        """No bulk-approve, no auto-approve, no admin override endpoint.

        If a second approval route is ever added, this fails and forces the author to
        justify it — the API-level counterpart to the state machine reflection test.
        """
        approval_routes = {
            (path, method) for path, method in _paths(live_schema) if "approve" in path.lower()
        }
        assert approval_routes == {("/api/v1/documents/{document_id}/approve", "POST")}

    def test_approve_requires_content_hash_and_confirmation(self, live_schema):
        """Both fields are required with no default — approval cannot happen by accident."""
        operation = live_schema["paths"]["/api/v1/documents/{document_id}/approve"]["post"]
        ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        schema = live_schema["components"]["schemas"][ref.split("/")[-1]]

        assert set(schema["required"]) >= {"content_hash", "confirm_reviewed"}

    def test_confirm_reviewed_accepts_only_literal_true(self, live_schema):
        """A `false` or omitted value must not be a valid request.

        Typed as Literal[True], so the schema constrains it to a single value — the
        request is rejected before any handler runs.
        """
        operation = live_schema["paths"]["/api/v1/documents/{document_id}/approve"]["post"]
        ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        schema = live_schema["components"]["schemas"][ref.split("/")[-1]]

        field = schema["properties"]["confirm_reviewed"]
        assert field.get("const") is True or field.get("enum") == [True], (
            f"confirm_reviewed must be constrained to literal true; got {field}"
        )

    def test_approval_response_names_the_accountable_human(self, live_schema):
        """The approval record must identify who took responsibility (Principle VIII)."""
        schema = live_schema["components"]["schemas"]["ApprovalRecordOut"]
        for field in ("approver_name", "approver_role", "approved_at", "content_hash"):
            assert field in schema["properties"], f"ApprovalRecordOut is missing {field}"


class TestGenerationContract:
    def test_generate_declares_the_failure_responses(self, contract):
        """451, 422, and 503 are part of the contract — failure is a documented outcome.

        A contract that only described the success case would let a future
        implementation return a partial draft on failure without breaking anything.
        """
        responses = contract["paths"]["/documents"]["post"]["responses"]
        for code in ("422", "451", "503"):
            assert code in responses, f"POST /documents must document a {code} response"

    def test_document_detail_always_marks_content_as_ai_generated(self, live_schema):
        """FR-020 — the label is structural, not a UI choice."""
        schema = live_schema["components"]["schemas"]["DocumentDetail"]
        field = schema["properties"]["ai_generated"]
        assert field.get("const") is True or field.get("enum") == [True]

    def test_document_detail_exposes_unresolved_gap_count(self, live_schema):
        """The client needs this to block approval before the request is even sent."""
        schema = live_schema["components"]["schemas"]["DocumentDetail"]
        assert "unresolved_gap_count" in schema["properties"]

    def test_sections_carry_evidence_and_gaps(self, live_schema):
        schema = live_schema["components"]["schemas"]["SectionOut"]
        for field in ("evidence_refs", "gaps", "confidence", "contains_external_data"):
            assert field in schema["properties"], f"SectionOut is missing {field}"

    def test_client_summary_asserts_synthetic_data(self, live_schema):
        """Principle VII surfaced in the API contract, not only in the database."""
        schema = live_schema["components"]["schemas"]["ClientSummary"]
        field = schema["properties"]["is_synthetic"]
        assert field.get("const") is True or field.get("enum") == [True]


class TestAuditIsReadOnly:
    def test_no_endpoint_mutates_an_audit_event(self, live_schema):
        """Contract invariant 3. No POST, PATCH, PUT, or DELETE touching audit."""
        mutating = {
            (path, method)
            for path, method in _paths(live_schema)
            if "audit" in path.lower() and method in {"POST", "PATCH", "PUT", "DELETE"}
        }
        assert not mutating, f"Audit records must be read-only over HTTP; found {mutating}"


class TestExportContract:
    def test_export_exists_and_is_read_only(self, live_schema):
        assert ("/api/v1/documents/{document_id}/export", "GET") in _paths(live_schema)

    def test_export_declares_a_conflict_response(self, contract):
        """409 when the document is not APPROVED."""
        responses = contract["paths"]["/documents/{document_id}/export"]["get"]["responses"]
        assert "409" in responses
