"""Quote verification — provider-agnostic grounding for models without native citations.

Anthropic returns citations the API itself produced: a `cited_text` span with a real
page or character locator, computed server-side from the document. We trust that
because the provider computed it, not the model.

Gemini has no equivalent for uploaded documents. Asking a model to *report* its own
citation offsets is worthless — a model that will invent a turnover figure will just as
happily invent the character position it came from.

So this module inverts the trust. The model is asked only for a **verbatim quote**, and
this code then searches the actual source text for that quote:

    found     → the claim is grounded, and we compute the locator ourselves
    not found → the claim is discarded

That makes the guarantee ours rather than the provider's. A model cannot fabricate its
way past a string search of a document it does not control.

**This module deliberately does no fuzzy matching.** Approximate matching is exactly the
loophole that would let a subtly-altered quote through — "KWD 4,500,000" against a source
saying "KWD 4,300,000" is a near-match and a catastrophe. The only tolerance permitted is
whitespace normalisation, because models routinely re-wrap lines without changing a word.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Collapse runs of whitespace (including newlines) to a single space. A model quoting
# across a line break is quoting faithfully; a model changing a digit is not.
_WHITESPACE = re.compile(r"\s+")

# Typographic substitutions models make when echoing text. Normalising these is safe:
# none of them can change a number, a name, or a negation.
_EQUIVALENTS = {
    "‘": "'",
    "’": "'",  # curly single quotes
    "“": '"',
    "”": '"',  # curly double quotes
    "–": "-",
    "—": "-",  # en/em dash
    " ": " ",  # non-breaking space
}

# A quote shorter than this proves nothing — "KWD" appears everywhere, and matching it
# would mark an invented claim as grounded.
MIN_QUOTE_LENGTH = 12


@dataclass(frozen=True)
class VerifiedQuote:
    """A quote confirmed to exist in the source, with the locator we computed."""

    quote: str
    char_start: int
    char_end: int
    exact: bool
    """True if found byte-for-byte; False if found only after whitespace normalisation."""


@dataclass(frozen=True)
class RejectedQuote:
    """A quote that could not be found in the source. The claim must be discarded."""

    quote: str
    reason: str


def _normalise(text: str) -> str:
    for src, dst in _EQUIVALENTS.items():
        text = text.replace(src, dst)
    return _WHITESPACE.sub(" ", text).strip()


def verify_quote(quote: str, source: str) -> VerifiedQuote | RejectedQuote:
    """Confirm a quote appears in the source, and locate it.

    Two passes, in order of strictness:

    1. **Exact** — the quote appears byte-for-byte. Offsets are the real ones.
    2. **Whitespace-normalised** — the quote appears once line wrapping and typographic
       quotes are normalised. Offsets are mapped back to the original text by locating
       the first and last words, which is approximate at the edges but correct about
       *which passage* is cited.

    Anything else is rejected. There is no third pass.
    """
    if not quote or not quote.strip():
        return RejectedQuote(quote=quote, reason="empty quote")

    stripped = quote.strip()

    if len(stripped) < MIN_QUOTE_LENGTH:
        return RejectedQuote(
            quote=stripped,
            reason=(
                f"quote is {len(stripped)} characters; under {MIN_QUOTE_LENGTH} a match "
                "proves nothing"
            ),
        )

    # Pass 1 — exact.
    index = source.find(stripped)
    if index >= 0:
        return VerifiedQuote(
            quote=stripped,
            char_start=index,
            char_end=index + len(stripped),
            exact=True,
        )

    # Pass 2 — whitespace and typography normalised.
    normalised_source = _normalise(source)
    normalised_quote = _normalise(stripped)

    if normalised_quote and normalised_quote in normalised_source:
        span = _map_back(stripped, source)
        if span is not None:
            return VerifiedQuote(quote=stripped, char_start=span[0], char_end=span[1], exact=False)
        # Present after normalisation but unlocatable in the original. Accept the claim
        # — it is genuinely in the document — but report a zero-width locator rather
        # than a guessed range, so nothing downstream shows the RM a false position.
        return VerifiedQuote(quote=stripped, char_start=0, char_end=0, exact=False)

    return RejectedQuote(
        quote=stripped,
        reason="quote does not appear in the source document",
    )


def _map_back(quote: str, source: str) -> tuple[int, int] | None:
    """Locate a whitespace-normalised quote in the original text.

    Anchors on the first and last word of the quote. Both must be present, and in that
    order, or no span is reported — a plausible-looking wrong range would be worse than
    admitting we cannot pinpoint it.
    """
    words = _normalise(quote).split(" ")
    if len(words) < 2:
        return None

    first, last = words[0], words[-1]

    start = source.find(first)
    if start < 0:
        return None

    end = source.find(last, start + len(first))
    if end < 0:
        return None

    return start, end + len(last)


@dataclass
class VerificationReport:
    """Outcome of verifying every quote in one grounding pass."""

    verified: list[VerifiedQuote]
    rejected: list[RejectedQuote]

    @property
    def total(self) -> int:
        return len(self.verified) + len(self.rejected)

    @property
    def rejection_rate(self) -> float:
        return len(self.rejected) / self.total if self.total else 0.0

    def summary(self) -> str:
        return (
            f"{len(self.verified)}/{self.total} quotes verified against source "
            f"({len(self.rejected)} discarded as ungrounded)"
        )


def verify_all(quotes: list[str], source: str) -> VerificationReport:
    """Verify a batch of quotes, partitioning them into grounded and discarded."""
    verified: list[VerifiedQuote] = []
    rejected: list[RejectedQuote] = []

    for quote in quotes:
        result = verify_quote(quote, source)
        if isinstance(result, VerifiedQuote):
            verified.append(result)
        else:
            rejected.append(result)

    return VerificationReport(verified=verified, rejected=rejected)
