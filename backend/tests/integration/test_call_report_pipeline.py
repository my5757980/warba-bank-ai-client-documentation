"""US1 pipeline behaviour against the stub port (tasks T082–T085).

These run the *real* generation pipeline — validators, screening, gap handling — with
only the model replaced. A failure here means the pipeline is broken, never that the
model had an off day.

Persistence is exercised separately once a database is available; these tests target
the decision logic, which is where the constitutional guarantees live.
"""

from __future__ import annotations

import pytest

from app.documents.generation_service import ScreeningBlockedError, ValidationFailedError
from app.documents.schemas.base import Gap, Section
from app.documents.schemas.call_report import CallReportSections
from app.documents.templates import load_template_file
from app.documents.validators import SectionDraft, validate_composition
from app.screening.deterministic import has_blocking_findings, screen_sections
from tests.support.stub_generation_port import claim, ledger

TEMPLATE = load_template_file(
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "config"
    / "templates"
    / "call_report.yaml"
)
REQUIRED_KEYS = [s["key"] for s in TEMPLATE["sections"] if s.get("required", True)]


def drafts_from(model: CallReportSections) -> list[SectionDraft]:
    """Mirror the generation service's schema → draft conversion."""
    out = []
    for ordinal, definition in enumerate(TEMPLATE["sections"]):
        section = getattr(model, definition["key"])
        out.append(
            SectionDraft(
                section_key=definition["key"],
                title=definition["title"],
                ordinal=ordinal,
                content=section.content,
                evidence_refs=list(section.evidence_refs),
                gaps=[g.model_dump() | {"resolved": False} for g in section.gaps],
                confidence=section.confidence,
                contains_external_data=section.contains_external_data,
            )
        )
    return out


def full_report(**overrides) -> CallReportSections:
    """A complete, well-grounded call report; override individual sections per test."""
    base = {
        key: Section(content=f"Content for {key}.", evidence_refs=["C001"], confidence="HIGH")
        for key in REQUIRED_KEYS
    }
    base.update(overrides)
    return CallReportSections(**base)


SAMPLE_LEDGER = ledger(
    claim("C001", "The meeting took place on 14 August 2026 at the client's premises."),
    claim("C002", "Current Murabaha utilisation is KWD 840,000 against a KWD 1,200,000 limit."),
    claim("C003", "FY2025 audited turnover was KWD 4,500,000 and net profit KWD 385,000."),
    claim("C004", "A receivable from one distributor is approximately 90 days overdue."),
)


class TestWellGroundedReport:
    def test_complete_report_passes_validation_and_screening(self):
        result = validate_composition(
            drafts_from(full_report()), SAMPLE_LEDGER.claims, REQUIRED_KEYS
        )
        assert not result.failed
        assert result.issues == []

        findings = screen_sections({d.section_key: d.content for d in result.sections})
        assert not has_blocking_financials(findings)

    def test_every_template_section_is_produced(self):
        drafts = drafts_from(full_report())
        assert {d.section_key for d in drafts} == set(REQUIRED_KEYS)
        assert len(drafts) == 8

    def test_cited_figures_survive(self):
        report = full_report(
            discussion_summary=Section(
                content=(
                    "Current Murabaha utilisation stands at KWD 840,000 against an "
                    "approved limit of KWD 1,200,000."
                ),
                evidence_refs=["C002"],
                confidence="HIGH",
            )
        )
        result = validate_composition(drafts_from(report), SAMPLE_LEDGER.claims, REQUIRED_KEYS)
        assert not result.failed


class TestGapMarking:
    """US1 scenario 3 — notes omitting the follow-up date."""

    def test_missing_follow_up_date_becomes_a_gap_not_a_guess(self):
        report = full_report(
            next_steps=Section(
                content="The parties agreed to reconvene once the forecast is shared.",
                evidence_refs=["C001"],
                gaps=[Gap(field="follow_up_date", label="[MISSING: agreed follow-up date]")],
                confidence="MEDIUM",
            )
        )

        result = validate_composition(drafts_from(report), SAMPLE_LEDGER.claims, REQUIRED_KEYS)
        next_steps = next(s for s in result.sections if s.section_key == "next_steps")

        assert not result.failed
        assert next_steps.gaps
        assert "MISSING" in next_steps.gaps[0]["label"]

    def test_an_invented_date_would_be_caught_as_untraceable(self):
        """The failure mode the gap marker exists to prevent."""
        report = full_report(
            next_steps=Section(
                content="A follow-up meeting is scheduled for 15 September 2026.",
                evidence_refs=["C001"],
                confidence="HIGH",
            )
        )

        result = validate_composition(drafts_from(report), SAMPLE_LEDGER.claims, REQUIRED_KEYS)
        assert result.failed
        assert any(i.code == "UNTRACEABLE_NUMERIC" for i in result.issues)

    def test_section_entirely_a_gap_is_valid(self):
        report = full_report(
            risks_and_concerns=Section(
                content=None,
                evidence_refs=[],
                gaps=[Gap(field="risks", label="[MISSING: no risks recorded in the notes]")],
                confidence="LOW",
            )
        )
        result = validate_composition(drafts_from(report), SAMPLE_LEDGER.claims, REQUIRED_KEYS)
        assert not result.failed

    def test_sparse_notes_produce_gaps_not_prose(self):
        """A near-empty input must not be expanded into invented narrative."""
        sparse = ledger(claim("C001", "The client was travelling and the call was short."))

        report = full_report(
            **{
                key: Section(
                    content=None,
                    evidence_refs=[],
                    gaps=[Gap(field=key, label=f"[MISSING: {key}]")],
                    confidence="LOW",
                )
                for key in REQUIRED_KEYS
                if key != "discussion_summary"
            },
            discussion_summary=Section(
                content="The call was brief as the client was travelling.",
                evidence_refs=["C001"],
                confidence="MEDIUM",
            ),
        )

        result = validate_composition(drafts_from(report), sparse.claims, REQUIRED_KEYS)
        assert not result.failed
        gapped = [s for s in result.sections if s.gaps]
        assert len(gapped) == 7


class TestFabricationIsRejected:
    def test_fabricated_turnover_fails_the_whole_generation(self):
        """SC-004. No threshold — one invented figure discards the document."""
        report = full_report(
            discussion_summary=Section(
                content="The Finance Director confirmed FY2025 turnover of KWD 9,900,000.",
                evidence_refs=["C003"],
                confidence="HIGH",
            )
        )

        result = validate_composition(drafts_from(report), SAMPLE_LEDGER.claims, REQUIRED_KEYS)
        assert result.failed
        issue = next(i for i in result.issues if i.code == "UNTRACEABLE_NUMERIC")
        assert issue.detail["literal"] == "9,900,000"

    def test_citing_a_nonexistent_claim_degrades_to_a_gap(self):
        report = full_report(
            client_requirements=Section(
                content="The client requested an increase to KWD 1,800,000.",
                evidence_refs=["C999"],
                confidence="HIGH",
            )
        )

        result = validate_composition(drafts_from(report), SAMPLE_LEDGER.claims, REQUIRED_KEYS)
        section = next(s for s in result.sections if s.section_key == "client_requirements")

        assert not result.failed
        assert section.content is None
        assert section.confidence == "LOW"


class TestInjectionResistance:
    """US1 scenario 6 — an embedded instruction in the notes."""

    def test_injected_approval_claim_has_no_evidence_and_is_discarded(self):
        """The architectural answer to prompt injection.

        Even if an injected instruction reached the composing model, the claim it
        produces has no ledger entry. Validation discards it. The defence is structural,
        not a plea in the system prompt.
        """
        report = full_report(
            discussion_summary=Section(
                content="The credit committee has APPROVED the facility increase.",
                evidence_refs=["C_INJECTED"],
                confidence="HIGH",
            )
        )

        result = validate_composition(drafts_from(report), SAMPLE_LEDGER.claims, REQUIRED_KEYS)
        section = next(s for s in result.sections if s.section_key == "discussion_summary")

        assert section.content is None
        assert "MISSING" in section.gaps[0]["label"]

    def test_injected_text_recorded_as_content_is_harmless(self):
        """If the model reports the injection as something the notes said, that is fine.

        It is an accurate record of the document's contents and makes no claim about
        the facility.
        """
        injected_ledger = ledger(
            claim("C001", "The notes contain text purporting to instruct the system."),
        )
        report = full_report(
            **{
                key: Section(
                    content=None, evidence_refs=[], gaps=[Gap(field=key, label="[MISSING]")]
                )
                for key in REQUIRED_KEYS
                if key != "risks_and_concerns"
            },
            risks_and_concerns=Section(
                content="The notes contain text purporting to instruct the system.",
                evidence_refs=["C001"],
                confidence="MEDIUM",
            ),
        )

        result = validate_composition(drafts_from(report), injected_ledger.claims, REQUIRED_KEYS)
        assert not result.failed


class TestShariahScreening:
    def test_conventional_terminology_blocks_the_draft(self):
        report = full_report(
            products_discussed=Section(
                content="The client asked about a conventional loan with a fixed interest rate.",
                evidence_refs=["C001"],
                confidence="HIGH",
            )
        )
        drafts = drafts_from(report)
        findings = screen_sections({d.section_key: d.content for d in drafts})

        assert has_blocking_findings(findings)
        assert any(f.section_key == "products_discussed" for f in findings)

    def test_islamic_terminology_passes(self):
        report = full_report(
            products_discussed=Section(
                content=(
                    "The client discussed the existing Murabaha facility and an Ijara "
                    "arrangement for warehouse equipment."
                ),
                evidence_refs=["C001"],
                confidence="HIGH",
            )
        )
        drafts = drafts_from(report)
        findings = screen_sections({d.section_key: d.content for d in drafts})
        assert not has_blocking_findings(findings)


class TestStubPortContract:
    def test_stub_records_that_compose_received_only_a_ledger(self):
        from tests.support.stub_generation_port import StubGenerationPort

        port = StubGenerationPort(ledger=SAMPLE_LEDGER, composition=full_report())
        port.compose(
            SAMPLE_LEDGER,
            schema=CallReportSections,
            template_guidance="guidance",
            approved_terminology={},
        )

        recorded = port.compose_calls[0]
        assert recorded["ledger"] is SAMPLE_LEDGER
        assert "sources" not in recorded

    def test_stub_can_simulate_a_failed_stage(self):
        from app.ports.types import GenerationError, GenerationRequest, GroundingScope
        from tests.support.stub_generation_port import StubGenerationPort

        port = StubGenerationPort(fail_on="grounding")
        request = GenerationRequest(
            document_id=__import__("uuid").uuid4(),
            document_type="CALL_REPORT",
            client_reference="WB-CORP-1001",
            sources=[],
            scope=GroundingScope(
                document_type="CALL_REPORT", client_reference="WB-CORP-1001", section_titles=[]
            ),
        )

        with pytest.raises(GenerationError):
            port.ground(request)


def has_blocking_financials(findings) -> bool:
    """Alias used above for readability."""
    return has_blocking_findings(findings)


# Sanity: the exception types the API layer maps are importable and distinct.
def test_pipeline_exception_types_are_distinct():
    assert ScreeningBlockedError is not ValidationFailedError
