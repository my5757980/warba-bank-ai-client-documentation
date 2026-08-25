"""Deterministic Shariah screening — the binding gate (research.md R5).

Constitution Principle II is NON-NEGOTIABLE, and a non-negotiable control cannot rest
on a probabilistic check. This module is a word-boundary matcher over a reviewable
vocabulary: identical input always produces identical findings, a Shariah stakeholder
can audit the rules without reading code, and there is no model in the path.

The semantic layer (`app.screening.semantic`) may add findings. Nothing may clear a
block raised here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from app.screening.vocabulary import ProhibitedTerm, Vocabulary, get_vocabulary


@dataclass(frozen=True)
class Finding:
    """One prohibited-term hit."""

    term: str
    rule_id: str
    severity: str
    rationale: str
    section_key: str
    offset: int
    matched_text: str

    @property
    def blocks(self) -> bool:
        return self.severity == "BLOCK"

    def to_dict(self) -> dict:
        return {
            "term": self.term,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "rationale": self.rationale,
            "section_key": self.section_key,
            "offset": self.offset,
            "matched_text": self.matched_text,
        }


@lru_cache(maxsize=512)
def _compile_pattern(term: str) -> re.Pattern[str]:
    r"""Compile a word-boundary, case-insensitive pattern for one term.

    Word boundaries matter more than they look. Without them, "interest" matches
    "interested" and "disinterested", producing false blocks that would train users
    to ignore the gate — the worst possible outcome for a safety control.

    Multi-word terms allow flexible internal whitespace so a line break inside
    "conventional  loan" does not defeat the match.
    """
    escaped = r"\s+".join(re.escape(part) for part in term.split())
    return re.compile(rf"\b{escaped}\b", re.IGNORECASE)


def _scan(text: str, terms: tuple[ProhibitedTerm, ...], section_key: str) -> list[Finding]:
    findings: list[Finding] = []
    for entry in terms:
        for match in _compile_pattern(entry.term).finditer(text):
            findings.append(
                Finding(
                    term=entry.term,
                    rule_id=entry.rule_id,
                    severity=entry.severity,
                    rationale=entry.rationale,
                    section_key=section_key,
                    offset=match.start(),
                    matched_text=match.group(0),
                )
            )
    return findings


def screen_text(
    text: str,
    *,
    section_key: str = "input",
    vocabulary: Vocabulary | None = None,
    include_decisioning: bool = False,
) -> list[Finding]:
    """Screen one block of text.

    `include_decisioning` adds the DT3 exclusions (ratings, recommendations, pricing).
    Those are not a Shariah control, but they run through the same deterministic
    machinery so the credit memo's boundaries do not depend on prompt compliance
    (spec.md §5 DT3, task T144).
    """
    if not text:
        return []

    vocab = vocabulary or get_vocabulary()
    terms = vocab.shariah_terms()
    if include_decisioning:
        terms = terms + vocab.decisioning_terms()

    findings = _scan(text, terms, section_key)
    # Longest term first at a given offset: "interest rate" (SH-001) is a more useful
    # finding than the bare "interest" (SH-002) it contains.
    findings.sort(key=lambda f: (f.offset, -len(f.term)))
    return _deduplicate_overlaps(findings)


def _deduplicate_overlaps(findings: list[Finding]) -> list[Finding]:
    """Drop shorter findings fully contained inside a longer one at the same place.

    Reporting both "interest rate" and "interest" for the same eight characters is
    noise, and noise in a compliance report is how real findings get missed.
    """
    kept: list[Finding] = []
    for finding in findings:
        start, end = finding.offset, finding.offset + len(finding.matched_text)
        contained = any(
            k.section_key == finding.section_key
            and k.offset <= start
            and (k.offset + len(k.matched_text)) >= end
            for k in kept
        )
        if not contained:
            kept.append(finding)
    return kept


def screen_sections(
    sections: dict[str, str | None],
    *,
    vocabulary: Vocabulary | None = None,
    include_decisioning: bool = False,
) -> list[Finding]:
    """Screen every section of a draft, keyed by section_key."""
    vocab = vocabulary or get_vocabulary()
    findings: list[Finding] = []
    for section_key, content in sections.items():
        if content:
            findings.extend(
                screen_text(
                    content,
                    section_key=section_key,
                    vocabulary=vocab,
                    include_decisioning=include_decisioning,
                )
            )
    return findings


def has_blocking_findings(findings: list[Finding]) -> bool:
    """Whether any finding blocks display of the draft."""
    return any(f.blocks for f in findings)
