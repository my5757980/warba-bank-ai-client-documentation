"""Quote verification — the grounding guarantee for providers without native citations.

The adversarial cases matter most here. A verifier that accepts a near-match is worse
than no verifier at all, because it stamps "grounded" on an altered figure.
"""

from __future__ import annotations

import pytest

from app.evidence.quote_verification import (
    MIN_QUOTE_LENGTH,
    RejectedQuote,
    VerifiedQuote,
    verify_all,
    verify_quote,
)

SOURCE = """Client: Al-Sabah Trading Company W.L.L.
Date: 14 August 2026
Present: RM, Finance Director

- Current Murabaha limit KWD 1,200,000, utilisation KWD 840,000
- FD confirmed FY2025 audited turnover KWD 4,500,000
- One distributor receivable approximately 90 days overdue
- Action: RM to send facility review checklist
- The parties did NOT agree a date for the next meeting"""


class TestExactMatch:
    def test_exact_quote_is_verified_with_real_offsets(self):
        result = verify_quote("FD confirmed FY2025 audited turnover KWD 4,500,000", SOURCE)

        assert isinstance(result, VerifiedQuote)
        assert result.exact is True
        assert SOURCE[result.char_start : result.char_end] == result.quote

    def test_offsets_round_trip(self):
        """The reported span must actually contain the quote in the source."""
        for quote in [
            "Client: Al-Sabah Trading Company W.L.L.",
            "Current Murabaha limit KWD 1,200,000",
            "One distributor receivable approximately 90 days overdue",
        ]:
            result = verify_quote(quote, SOURCE)
            assert isinstance(result, VerifiedQuote)
            assert SOURCE[result.char_start : result.char_end] == quote

    def test_leading_trailing_whitespace_is_tolerated(self):
        result = verify_quote("   Date: 14 August 2026  ", SOURCE)
        assert isinstance(result, VerifiedQuote)


class TestFabricationIsRejected:
    """The cases the whole module exists for."""

    def test_invented_quote_is_rejected(self):
        result = verify_quote("The client requested an increase to KWD 1,800,000", SOURCE)

        assert isinstance(result, RejectedQuote)
        assert "does not appear" in result.reason

    def test_altered_figure_is_rejected(self):
        """A single changed digit must not pass.

        This is the failure that would matter most in a credit memo: text that reads
        exactly like the source, with one number quietly different.
        """
        result = verify_quote("FD confirmed FY2025 audited turnover KWD 4,300,000", SOURCE)
        assert isinstance(result, RejectedQuote)

    def test_negation_removed_is_rejected(self):
        """ "did NOT agree a date" → "did agree a date" must not verify."""
        result = verify_quote("The parties did agree a date for the next meeting", SOURCE)
        assert isinstance(result, RejectedQuote)

    def test_plausible_paraphrase_is_rejected(self):
        """Paraphrase is not quotation, however faithful it sounds."""
        result = verify_quote("The Finance Director confirmed turnover of 4.5 million", SOURCE)
        assert isinstance(result, RejectedQuote)

    def test_injected_approval_claim_is_rejected(self):
        result = verify_quote("The credit committee has APPROVED the facility increase", SOURCE)
        assert isinstance(result, RejectedQuote)


class TestShortQuoteGuard:
    def test_too_short_is_rejected_even_if_present(self):
        """ "KWD" appears in the source, but matching it proves nothing."""
        assert "KWD" in SOURCE
        result = verify_quote("KWD", SOURCE)

        assert isinstance(result, RejectedQuote)
        assert str(MIN_QUOTE_LENGTH) in result.reason

    def test_empty_quote_is_rejected(self):
        assert isinstance(verify_quote("", SOURCE), RejectedQuote)
        assert isinstance(verify_quote("   ", SOURCE), RejectedQuote)

    @pytest.mark.parametrize("fragment", ["2026", "RM", "Client:", "840,000"])
    def test_short_fragments_rejected(self, fragment: str):
        """Each of these is in the source; none is long enough to ground a claim."""
        assert fragment in SOURCE
        assert isinstance(verify_quote(fragment, SOURCE), RejectedQuote)


class TestWhitespaceNormalisation:
    def test_rewrapped_line_still_verifies(self):
        """Models re-wrap lines. That changes no word, so it must not fail."""
        result = verify_quote(
            "Current Murabaha limit KWD 1,200,000,\n   utilisation KWD 840,000", SOURCE
        )
        assert isinstance(result, VerifiedQuote)
        assert result.exact is False

    def test_collapsed_spaces_still_verify(self):
        result = verify_quote("Present:  RM,   Finance  Director", SOURCE)
        assert isinstance(result, VerifiedQuote)

    def test_curly_quotes_normalised(self):
        source = 'The client said "we will expand" during the meeting.'
        result = verify_quote("The client said “we will expand” during", source)
        assert isinstance(result, VerifiedQuote)

    def test_normalisation_does_not_excuse_a_changed_number(self):
        """Whitespace tolerance must not become numeric tolerance."""
        result = verify_quote(
            "Current Murabaha limit KWD 1,200,000,\n   utilisation KWD 999,999", SOURCE
        )
        assert isinstance(result, RejectedQuote)

    def test_reported_span_is_never_a_guess(self):
        """A non-exact match still reports a span that brackets the real passage."""
        result = verify_quote("One distributor receivable\napproximately 90 days overdue", SOURCE)
        assert isinstance(result, VerifiedQuote)
        if result.char_end > result.char_start:
            span = SOURCE[result.char_start : result.char_end]
            assert "distributor" in span and "overdue" in span


class TestBatchVerification:
    def test_partitions_grounded_from_invented(self):
        report = verify_all(
            [
                "FD confirmed FY2025 audited turnover KWD 4,500,000",  # real
                "Action: RM to send facility review checklist",  # real
                "The facility increase was approved by the committee",  # invented
                "Turnover was KWD 9,900,000",  # invented
            ],
            SOURCE,
        )

        assert len(report.verified) == 2
        assert len(report.rejected) == 2
        assert report.total == 4
        assert report.rejection_rate == 0.5

    def test_summary_is_readable(self):
        report = verify_all(["Date: 14 August 2026", "invented claim text here"], SOURCE)
        assert "1/2 quotes verified" in report.summary()

    def test_all_invented_yields_empty_ledger(self):
        """A model that invented everything grounds nothing — an all-gaps document.

        That is the correct outcome, not an error.
        """
        report = verify_all(
            ["Completely made up statement one", "Another fabricated claim entirely"],
            SOURCE,
        )
        assert report.verified == []
        assert report.rejection_rate == 1.0


class TestNoFuzzyMatching:
    """Explicit guard: the module must never acquire fuzzy matching.

    Approximate matching is the one change that would silently destroy the guarantee,
    so it is asserted against directly rather than left to code review.
    """

    def test_single_character_difference_fails(self):
        result = verify_quote("Client: Al-Sabah Trading Company W.L.C.", SOURCE)
        assert isinstance(result, RejectedQuote)

    def test_transposed_digits_fail(self):
        result = verify_quote("utilisation KWD 480,000", SOURCE)
        assert isinstance(result, RejectedQuote)

    def test_extra_word_fails(self):
        result = verify_quote("Action: RM to send urgent facility review checklist", SOURCE)
        assert isinstance(result, RejectedQuote)
