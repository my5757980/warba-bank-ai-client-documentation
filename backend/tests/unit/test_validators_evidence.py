"""Evidence reference resolution and section coverage (tasks T058, T060)."""

from __future__ import annotations

from dataclasses import dataclass

from app.documents.validators import (
    SectionDraft,
    validate_composition,
    validate_evidence_refs,
    validate_section_coverage,
)


@dataclass
class FakeClaim:
    claim_id: str
    text: str = "A grounded fact."

    @property
    def searchable_text(self) -> str:
        return self.text


def draft(key: str, content: str | None, refs: list[str], gaps: list[dict] | None = None):
    return SectionDraft(
        section_key=key,
        title=key.replace("_", " ").title(),
        ordinal=0,
        content=content,
        evidence_refs=refs,
        gaps=gaps or [],
    )


class TestEvidenceResolution:
    def test_resolvable_refs_pass_through_untouched(self):
        claims = [FakeClaim("C1"), FakeClaim("C2")]
        section = draft("summary", "The client expanded operations.", ["C1", "C2"])
        result = validate_evidence_refs([section], claims)

        assert result.issues == []
        assert result.sections[0].content == "The client expanded operations."

    def test_unresolvable_ref_converts_section_to_gap(self):
        """A cited claim that does not exist means the content is unsourced.

        Rather than discard the whole generation, the section degrades to a gap: the
        RM is told the information could not be sourced, which is true and useful,
        instead of being shown prose with a citation pointing at nothing.
        """
        claims = [FakeClaim("C1")]
        section = draft("summary", "The client plans to expand.", ["C1", "C99"])
        result = validate_evidence_refs([section], claims)

        assert len(result.issues) == 1
        assert result.issues[0].code == "UNRESOLVED_EVIDENCE_REF"
        assert result.issues[0].detail["unresolved_refs"] == ["C99"]

        out = result.sections[0]
        assert out.content is None
        assert out.evidence_refs == ["C1"]
        assert out.confidence == "LOW"
        assert "MISSING" in out.gaps[0]["label"]

    def test_unresolvable_ref_is_not_fatal(self):
        """Degrading to a gap is recoverable; a fabricated number is not."""
        result = validate_evidence_refs([draft("s", "text", ["C99"])], [FakeClaim("C1")])
        assert not result.failed

    def test_empty_ledger_gaps_every_cited_section(self):
        """A client with no records yields an all-gaps document, not invented prose."""
        section = draft("summary", "The client is performing well.", ["C1"])
        result = validate_evidence_refs([section], [])

        assert result.sections[0].content is None
        assert result.sections[0].gaps

    def test_section_with_no_refs_is_untouched(self):
        section = draft("next_steps", "Follow up next quarter.", [])
        result = validate_evidence_refs([section], [])
        assert result.sections[0].content == "Follow up next quarter."


class TestSectionCoverage:
    def test_complete_coverage_passes(self):
        sections = [draft("a", "text", []), draft("b", "text", [])]
        result = validate_section_coverage(sections, ["a", "b"])
        assert result.issues == []

    def test_missing_required_section_is_fatal(self):
        """An absent section is worse than one marked missing.

        Absence is silent — the RM cannot see what they were not told.
        """
        result = validate_section_coverage([draft("a", "text", [])], ["a", "b"])

        assert result.failed
        assert result.issues[0].code == "MISSING_REQUIRED_SECTION"
        assert result.issues[0].section_key == "b"

    def test_empty_section_gets_a_gap_marker(self):
        result = validate_section_coverage([draft("a", None, [])], ["a"])

        assert result.issues[0].code == "EMPTY_SECTION_NO_GAP"
        assert result.sections[0].gaps
        assert result.sections[0].confidence == "LOW"

    def test_section_that_is_entirely_a_gap_is_valid(self):
        """Gaps are a first-class output state, not an error."""
        section = draft("a", None, [], gaps=[{"field": "a", "label": "[MISSING: x]"}])
        result = validate_section_coverage([section], ["a"])
        assert result.issues == []
        assert not result.failed

    def test_optional_section_may_be_absent(self):
        result = validate_section_coverage([draft("a", "text", [])], ["a"])
        assert result.issues == []


class TestCombinedPipeline:
    def test_order_matters_gapped_section_skips_numeric_check(self):
        """Evidence resolution runs first.

        A section converted to a gap has no content left, so its numbers cannot fail
        the numeric check afterwards. Running the checks in the other order would
        report a fabricated-figure failure for content that was already discarded.
        """
        claims = [FakeClaim("C1", "Turnover was KWD 4,500,000.")]
        section = draft("financials", "Turnover was KWD 9,999,999.", ["C99"])

        result = validate_composition([section], claims, ["financials"])

        assert not result.failed
        assert result.sections[0].content is None
        assert any(i.code == "UNRESOLVED_EVIDENCE_REF" for i in result.issues)
        assert not any(i.code == "UNTRACEABLE_NUMERIC" for i in result.issues)

    def test_valid_document_passes_all_three(self):
        claims = [FakeClaim("C1", "Turnover was KWD 4,500,000.")]
        section = draft("financials", "Turnover was KWD 4,500,000.", ["C1"])

        result = validate_composition([section], claims, ["financials"])

        assert result.issues == []
        assert not result.failed

    def test_fabricated_figure_with_valid_refs_still_fails(self):
        """The case the whole architecture exists to catch."""
        claims = [FakeClaim("C1", "Turnover was KWD 4,500,000.")]
        section = draft("financials", "Turnover was KWD 7,100,000.", ["C1"])

        result = validate_composition([section], claims, ["financials"])

        assert result.failed
        assert any(i.code == "UNTRACEABLE_NUMERIC" for i in result.issues)
