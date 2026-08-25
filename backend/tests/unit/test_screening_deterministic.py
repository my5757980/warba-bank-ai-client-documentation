"""Deterministic Shariah screening (task T043).

Constitution Principle II is NON-NEGOTIABLE. These tests assert the gate blocks what
it must, and — just as important — does not block what it must not. A gate with false
positives trains users to ignore it, which is the worst outcome for a safety control.
"""

from __future__ import annotations

import pytest

from app.screening.deterministic import (
    has_blocking_findings,
    screen_sections,
    screen_text,
)
from app.screening.vocabulary import get_vocabulary


class TestVocabularyLoading:
    def test_vocabulary_loads_with_a_version(self):
        vocab = get_vocabulary()
        assert vocab.version
        assert vocab.prohibited_terms
        assert vocab.approved_structures

    def test_approved_structures_include_core_islamic_products(self):
        names = get_vocabulary().structure_names
        for expected in ("murabaha", "ijara", "wakala", "musharaka", "mudaraba"):
            assert expected in names


class TestBlocking:
    def test_riba_sense_of_interest_is_blocked(self):
        """The riba senses block; the ordinary-English sense does not."""
        findings = screen_text("The facility carries interest of 5%.")
        assert has_blocking_findings(findings)
        assert all(f.rule_id.startswith("SH-002") for f in findings if f.blocks)

    def test_ordinary_english_interest_only_flags(self):
        """ "The client indicated interest in expanding" is not riba.

        Blocking it produced a false positive on a compliant control case in the
        evaluation harness. A gate that fires on correct content stops being read,
        so the bare term flags for attention instead of blocking.
        """
        findings = screen_text("The client indicated interest in fleet expansion.")
        assert not has_blocking_findings(findings)
        assert findings and findings[0].severity == "FLAG"

    def test_conventional_loan_is_blocked(self):
        findings = screen_text("We propose a conventional loan structure.")
        assert has_blocking_findings(findings)

    def test_riba_is_blocked(self):
        assert has_blocking_findings(screen_text("This avoids riba entirely."))

    def test_overdraft_is_blocked(self):
        assert has_blocking_findings(screen_text("An overdraft facility is available."))

    def test_prohibited_sector_is_blocked(self):
        assert has_blocking_findings(screen_text("The client operates a brewery."))

    def test_finding_carries_diagnostic_fields(self):
        finding = screen_text("Interest will accrue monthly.", section_key="terms")[0]
        assert finding.section_key == "terms"
        assert finding.rule_id
        assert finding.rationale
        assert finding.offset >= 0


class TestWordBoundaries:
    """False positives are as damaging as false negatives here."""

    def test_interested_does_not_match_interest(self):
        assert screen_text("The client is interested in expanding.") == []

    def test_disinterested_does_not_match(self):
        assert screen_text("A disinterested party reviewed the file.") == []

    def test_case_insensitive(self):
        assert has_blocking_findings(screen_text("INTEREST RATE of 4%"))
        assert has_blocking_findings(screen_text("Interest Rate of 4%"))

    def test_multiword_term_tolerates_line_break(self):
        assert has_blocking_findings(screen_text("a conventional\nloan was discussed"))


class TestCompliantContentPasses:
    def test_murabaha_narrative_is_clean(self):
        text = (
            "The client requested a Murabaha facility of KWD 500,000 for equipment "
            "acquisition. The profit rate will be agreed at the point of sale, and "
            "settlement is over 36 months."
        )
        assert screen_text(text) == []

    def test_ijara_narrative_is_clean(self):
        text = (
            "An Ijara Muntahia Bittamleek structure is proposed, with rentals payable "
            "quarterly and ownership transferring on final settlement."
        )
        assert screen_text(text) == []


class TestOverlapDeduplication:
    def test_longer_term_wins_at_same_position(self):
        """ "interest rate" is a more useful finding than the "interest" inside it."""
        findings = screen_text("The interest rate is fixed.")
        assert len(findings) == 1
        assert findings[0].term == "interest rate"


class TestDecisioningExclusions:
    """DT3 excludes ratings, recommendations, and pricing (task T144)."""

    def test_decisioning_not_screened_by_default(self):
        assert screen_text("We recommend approval of this facility.") == []

    def test_recommendation_blocked_when_enabled(self):
        findings = screen_text("We recommend approval of this facility.", include_decisioning=True)
        assert has_blocking_findings(findings)
        assert findings[0].rule_id.startswith("DEC-")

    def test_risk_rating_blocked_when_enabled(self):
        findings = screen_text("The internal rating is BB+.", include_decisioning=True)
        assert has_blocking_findings(findings)

    def test_pricing_blocked_when_enabled(self):
        findings = screen_text("A profit rate of 6.5% applies.", include_decisioning=True)
        assert has_blocking_findings(findings)


class TestSectionScreening:
    def test_findings_attributed_to_the_right_section(self):
        findings = screen_sections(
            {
                "background": "The client operates in logistics.",
                "structure": "A conventional loan is proposed.",
            }
        )
        assert len(findings) == 1
        assert findings[0].section_key == "structure"

    def test_empty_sections_are_skipped(self):
        assert screen_sections({"background": None, "structure": ""}) == []


class TestDeterminism:
    @pytest.mark.parametrize("run", range(5))
    def test_identical_input_gives_identical_findings(self, run: int):
        """A NON-NEGOTIABLE gate must be reproducible, not merely usually right."""
        text = "The conventional loan carries interest and the client runs a casino."
        first = [f.to_dict() for f in screen_text(text)]
        second = [f.to_dict() for f in screen_text(text)]
        assert first == second
