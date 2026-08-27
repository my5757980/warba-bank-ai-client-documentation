"""Deterministic post-composition validation (research.md R3).

This module is where "minimise hallucinations" stops being an aspiration and becomes a
machine-checkable property. The Composition Pass produces sections; nothing reaches an
RM until these checks pass:

  1. `validate_evidence_refs`  — every cited claim_id exists in the ledger.
  2. `validate_numeric_literals` — every number traces to a referenced claim.
  3. `validate_section_coverage` — every required section is present or gap-marked.

The model cannot defeat these by writing more convincingly, because they compare its
output against the ledger rather than judging the output on its own terms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


class ClaimLike(Protocol):
    """Minimal claim shape these validators need."""

    claim_id: str

    @property
    def searchable_text(self) -> str: ...


@dataclass
class SectionDraft:
    """A composed section before validation."""

    section_key: str
    title: str
    ordinal: int
    content: str | None
    evidence_refs: list[str] = field(default_factory=list)
    gaps: list[dict] = field(default_factory=list)
    confidence: str = "MEDIUM"
    contains_external_data: bool = False
    is_rm_edited: bool = False


@dataclass
class ValidationIssue:
    code: str
    section_key: str
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    sections: list[SectionDraft]
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        """Whether any issue is fatal.

        Unresolvable evidence refs are recoverable — the section degrades to a gap,
        which is an honest outcome. An untraceable number is not recoverable: it is a
        fabricated figure, and generation fails closed (SC-004).
        """
        return any(i.code in _FATAL_CODES for i in self.issues)


_FATAL_CODES = {"UNTRACEABLE_NUMERIC", "MISSING_REQUIRED_SECTION"}


# ---------------------------------------------------------------------------
# 1. Evidence reference resolution (FR-011)
# ---------------------------------------------------------------------------


def validate_evidence_refs(
    sections: list[SectionDraft],
    claims: list[ClaimLike],
) -> ValidationResult:
    """Every section with content must cite, and every citation must resolve.

    Two distinct failures, both meaning the same thing — the content is unsourced:

    1. **Unresolvable reference** — the model cited a claim id that is not in the ledger.
    2. **No reference at all** — the model wrote prose and cited nothing.

    The second was invisible for a long time. The Anthropic path always returned
    citations, so a section with zero `evidence_refs` never occurred and the code fell
    through the `if not unresolved` branch straight into the output. Running the same
    pipeline against a second provider produced exactly that case, and uncited prose
    reached the RM looking indistinguishable from grounded prose.

    FR-011 does not say "citations must resolve"; it says every factual statement must
    be traceable to a source. A section that cites nothing satisfies the first reading
    and fails the second, so both are handled here.

    In either case the section degrades to a gap rather than discarding the whole
    generation: the RM is told the information could not be sourced, which is true and
    useful, instead of being shown prose with nothing behind it.
    """
    known = {c.claim_id for c in claims}
    issues: list[ValidationIssue] = []
    out: list[SectionDraft] = []

    for section in sections:
        unresolved = [ref for ref in section.evidence_refs if ref not in known]
        has_content = bool(section.content and section.content.strip())
        uncited = has_content and not section.evidence_refs

        if not unresolved and not uncited:
            out.append(section)
            continue

        if uncited:
            issues.append(
                ValidationIssue(
                    code="UNCITED_CONTENT",
                    section_key=section.section_key,
                    message=(
                        f"Section '{section.section_key}' contains content but cites no "
                        "evidence. Unsourced content converted to a gap."
                    ),
                    detail={"content_length": len(section.content or "")},
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    code="UNRESOLVED_EVIDENCE_REF",
                    section_key=section.section_key,
                    message=(
                        f"Section '{section.section_key}' cited "
                        f"{len(unresolved)} claim(s) absent from the evidence ledger. "
                        "Content converted to a gap."
                    ),
                    detail={"unresolved_refs": unresolved},
                )
            )

        out.append(
            SectionDraft(
                section_key=section.section_key,
                title=section.title,
                ordinal=section.ordinal,
                content=None,
                evidence_refs=[r for r in section.evidence_refs if r in known],
                gaps=[
                    *section.gaps,
                    {
                        "field": section.section_key,
                        "label": f"[MISSING: {section.title} — could not be sourced]",
                        "resolved": False,
                        "resolution_note": None,
                    },
                ],
                confidence="LOW",
                contains_external_data=section.contains_external_data,
            )
        )

    return ValidationResult(sections=out, issues=issues)


# ---------------------------------------------------------------------------
# 2. Numeric literal tracing (SC-004 — the release gate)
# ---------------------------------------------------------------------------

# Matches integers, decimals, and thousands-separated figures, with optional
# currency prefix or percent suffix.
_NUMERIC_RE = re.compile(
    r"""
    (?<![\w.])
    (?:KWD|USD|EUR|GBP|AED|SAR)?\s*
    (\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*(?:%|percent|million|billion|bn|m|k)?
    (?![\w])
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Numbers that are structural rather than factual claims. A section that says
# "3 action items were agreed" is counting its own content, not asserting a
# sourced figure, and requiring evidence for it would produce false failures.
_STRUCTURAL_NUMERIC_MAX = 12


def _normalise_number(raw: str) -> str:
    """Strip separators so `1,250,000` and `1250000` compare equal."""
    return raw.replace(",", "").rstrip("0").rstrip(".") if "." in raw else raw.replace(",", "")


def extract_numerics(text: str) -> list[str]:
    """Every numeric literal in the text, as matched."""
    return [m.group(1) for m in _NUMERIC_RE.finditer(text)]


def validate_numeric_literals(
    sections: list[SectionDraft],
    claims: list[ClaimLike],
) -> ValidationResult:
    """Every number in section content must appear in a referenced claim.

    This is the mechanism behind SC-004. A figure that exists nowhere in the evidence
    is a fabrication, and there is no threshold — generation fails closed. A threshold
    would license some fabrication, and in a credit memo one invented turnover figure
    is one too many.

    Only claims the section actually cites are searched. Allowing a section to borrow
    a number from an unrelated claim elsewhere in the ledger would let a figure drift
    between contexts, which is a subtler form of the same error.
    """
    by_id = {c.claim_id: c for c in claims}
    issues: list[ValidationIssue] = []

    for section in sections:
        if not section.content:
            continue

        referenced = [by_id[r] for r in section.evidence_refs if r in by_id]
        haystack = "\n".join(c.searchable_text for c in referenced)
        normalised_haystack = {_normalise_number(n) for n in extract_numerics(haystack)}

        for literal in extract_numerics(section.content):
            normalised = _normalise_number(literal)

            # Small bare integers are structural (counts, list positions, ordinals).
            try:
                is_bare_int = "," not in literal and "." not in literal
                if is_bare_int and int(literal) <= _STRUCTURAL_NUMERIC_MAX:
                    continue
            except ValueError:  # pragma: no cover - regex guarantees digits
                pass

            # Four-digit values in a plausible year range are dates, not figures.
            is_year = (
                len(normalised) == 4 and normalised.isdigit() and 1900 <= int(normalised) <= 2100
            )
            if is_year and (
                normalised in normalised_haystack or _year_in_text(normalised, haystack)
            ):
                continue

            if normalised not in normalised_haystack:
                issues.append(
                    ValidationIssue(
                        code="UNTRACEABLE_NUMERIC",
                        section_key=section.section_key,
                        message=(
                            f"The figure '{literal}' in section "
                            f"'{section.section_key}' does not appear in any cited "
                            "evidence. Generation failed closed rather than present an "
                            "unsourced number."
                        ),
                        detail={
                            "literal": literal,
                            "cited_claims": [c.claim_id for c in referenced],
                        },
                    )
                )

    return ValidationResult(sections=sections, issues=issues)


def _year_in_text(year: str, text: str) -> bool:
    """Whether a four-digit year appears in the evidence.

    A plain substring check, deliberately. Word boundaries fail here: the evidence
    commonly writes `FY2025`, where there is no boundary between `Y` and `2`, so a
    `\\b`-anchored search would reject a year that is plainly present. Four consecutive
    digits in a valid year range are specific enough that substring matching does not
    meaningfully loosen the check.
    """
    return year in text


# ---------------------------------------------------------------------------
# 3. Section coverage (FR-009)
# ---------------------------------------------------------------------------


def validate_section_coverage(
    sections: list[SectionDraft],
    required_keys: list[str],
) -> ValidationResult:
    """Every template-mandated section must be present with content or a gap.

    A section that is simply absent is worse than one marked missing: the RM cannot
    see what they were not told. Absence is silent; a gap marker is not.
    """
    issues: list[ValidationIssue] = []
    present = {s.section_key: s for s in sections}

    for key in required_keys:
        section = present.get(key)

        if section is None:
            issues.append(
                ValidationIssue(
                    code="MISSING_REQUIRED_SECTION",
                    section_key=key,
                    message=f"Required section '{key}' is absent from the composed document.",
                )
            )
            continue

        if not section.content and not section.gaps:
            issues.append(
                ValidationIssue(
                    code="EMPTY_SECTION_NO_GAP",
                    section_key=key,
                    message=(
                        f"Section '{key}' has neither content nor a gap marker. "
                        "An empty section must state that information was unavailable."
                    ),
                )
            )
            section.gaps = [
                {
                    "field": key,
                    "label": f"[MISSING: {section.title}]",
                    "resolved": False,
                    "resolution_note": None,
                }
            ]
            section.confidence = "LOW"

    return ValidationResult(sections=sections, issues=issues)


# ---------------------------------------------------------------------------
# Combined pipeline
# ---------------------------------------------------------------------------


def validate_composition(
    sections: list[SectionDraft],
    claims: list[ClaimLike],
    required_keys: list[str],
) -> ValidationResult:
    """Run all three validators in order.

    Order matters: evidence resolution runs first because it can convert a section to
    a gap, and a section that became a gap has no content left to check for numbers.
    """
    ref_result = validate_evidence_refs(sections, claims)
    numeric_result = validate_numeric_literals(ref_result.sections, claims)
    coverage_result = validate_section_coverage(numeric_result.sections, required_keys)

    return ValidationResult(
        sections=coverage_result.sections,
        issues=[*ref_result.issues, *numeric_result.issues, *coverage_result.issues],
    )
