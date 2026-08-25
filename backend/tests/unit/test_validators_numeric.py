"""Numeric-literal tracing — the mechanism behind SC-004 (task T059).

SC-004 is a release gate with no threshold: zero fabricated figures. These tests
exercise the check that makes it enforceable.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.documents.validators import (
    SectionDraft,
    extract_numerics,
    validate_numeric_literals,
)


@dataclass
class FakeClaim:
    claim_id: str
    text: str

    @property
    def searchable_text(self) -> str:
        return self.text


def section(content: str, refs: list[str] | None = None) -> SectionDraft:
    return SectionDraft(
        section_key="financials",
        title="Financial Summary",
        ordinal=1,
        content=content,
        evidence_refs=refs or ["C1"],
    )


class TestExtraction:
    def test_extracts_plain_integers(self):
        assert "4500000" in [n.replace(",", "") for n in extract_numerics("Revenue was 4500000")]

    def test_extracts_thousands_separated(self):
        assert "4,500,000" in extract_numerics("Revenue was KWD 4,500,000 last year")

    def test_extracts_decimals(self):
        assert "12.5" in extract_numerics("Margin improved to 12.5%")

    def test_ignores_words(self):
        assert extract_numerics("No figures were discussed") == []


class TestTraceability:
    def test_traceable_figure_passes(self):
        claims = [FakeClaim("C1", "Audited turnover for FY2025 was KWD 4,500,000.")]
        result = validate_numeric_literals([section("Turnover was KWD 4,500,000.")], claims)
        assert result.issues == []
        assert not result.failed

    def test_untraceable_figure_fails_closed(self):
        """The core anti-hallucination assertion.

        The claim says 4,500,000. The section says 5,200,000. No threshold, no
        tolerance — this fails.
        """
        claims = [FakeClaim("C1", "Audited turnover for FY2025 was KWD 4,500,000.")]
        result = validate_numeric_literals([section("Turnover was KWD 5,200,000.")], claims)

        assert result.failed
        assert len(result.issues) == 1
        assert result.issues[0].code == "UNTRACEABLE_NUMERIC"
        assert result.issues[0].detail["literal"] == "5,200,000"

    def test_separator_formatting_does_not_matter(self):
        """`4,500,000` in the source and `4500000` in the output are the same figure."""
        claims = [FakeClaim("C1", "Turnover: 4500000 KWD")]
        result = validate_numeric_literals([section("Turnover was KWD 4,500,000.")], claims)
        assert not result.failed

    def test_percentage_traced(self):
        claims = [FakeClaim("C1", "Gross margin stood at 12.5% for the period.")]
        result = validate_numeric_literals([section("Margin was 12.5%.")], claims)
        assert not result.failed

    def test_untraceable_percentage_fails(self):
        claims = [FakeClaim("C1", "Gross margin stood at 12.5% for the period.")]
        result = validate_numeric_literals([section("Margin was 18.9%.")], claims)
        assert result.failed

    def test_figure_in_verbatim_excerpt_counts(self):
        """A figure phrased differently by the model still traces via the excerpt."""
        claims = [FakeClaim("C1", "The company reported strong revenue. [excerpt: KWD 4,500,000]")]
        result = validate_numeric_literals([section("Revenue reached KWD 4,500,000.")], claims)
        assert not result.failed


class TestScopeRules:
    def test_cannot_borrow_a_number_from_an_uncited_claim(self):
        """A section may only use figures from claims it actually cites.

        Otherwise a figure could drift between unrelated contexts — a subtler
        fabrication than inventing one outright, and harder to spot in review.
        """
        claims = [
            FakeClaim("C1", "Turnover was KWD 4,500,000."),
            FakeClaim("C2", "Headcount is 250."),
        ]
        result = validate_numeric_literals([section("Headcount is 250.", refs=["C1"])], claims)
        assert result.failed

    def test_small_integers_are_structural(self):
        """ "3 action items" is the section counting itself, not asserting a figure."""
        claims = [FakeClaim("C1", "The meeting covered several topics.")]
        result = validate_numeric_literals([section("There were 3 action items.")], claims)
        assert not result.failed

    def test_large_bare_integer_is_not_structural(self):
        claims = [FakeClaim("C1", "The meeting covered several topics.")]
        result = validate_numeric_literals([section("There were 4500 action items.")], claims)
        assert result.failed

    def test_year_present_in_evidence_passes(self):
        claims = [FakeClaim("C1", "The FY2025 statements were reviewed.")]
        result = validate_numeric_literals([section("The 2025 statements were reviewed.")], claims)
        assert not result.failed

    def test_section_without_content_is_skipped(self):
        empty = SectionDraft(
            section_key="financials", title="Financial Summary", ordinal=1, content=None
        )
        result = validate_numeric_literals([empty], [])
        assert result.issues == []


@pytest.mark.parametrize(
    "content,expect_failure",
    [
        ("Facility of KWD 750,000 requested.", False),
        ("Facility of KWD 950,000 requested.", True),
    ],
)
def test_credit_figures(content: str, expect_failure: bool):
    """The case that matters most: a facility amount in a credit memo."""
    claims = [FakeClaim("C1", "Client requested a facility of KWD 750,000.")]
    result = validate_numeric_literals([section(content)], claims)
    assert result.failed is expect_failure
