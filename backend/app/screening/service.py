"""Screening service — persistence and the input-side screen (tasks T041, T042).

The deterministic gate itself lives in `deterministic.py`. This module runs it against
persisted objects, records the result, and handles the input-side screen that flags a
non-compliant request before anything is drafted.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.documents.models import DocumentVersion
from app.enums import ScreeningLayer, ScreeningOutcome
from app.screening.deterministic import Finding, has_blocking_findings, screen_sections, screen_text
from app.screening.models import ScreeningResult
from app.screening.vocabulary import get_vocabulary


@dataclass
class InputScreenResult:
    """Outcome of screening RM-supplied input before generation."""

    findings: list[Finding]
    unmappable_product: bool

    @property
    def blocked(self) -> bool:
        return has_blocking_findings(self.findings)

    @property
    def should_flag(self) -> bool:
        return bool(self.findings) or self.unmappable_product


def screen_input(text: str, *, expect_product_reference: bool = False) -> InputScreenResult:
    """Screen RM input before drafting (FR-017).

    Two distinct concerns:

    1. Prohibited terminology in the request itself. If a client has asked for a
       conventional interest-bearing loan, that is flagged rather than quietly drafted
       as though it were compliant.

    2. A product reference that maps to no approved Islamic structure. Flagged, never
       guessed. Picking the "closest" structure would be the system inventing a product
       the bank has not agreed to offer.
    """
    findings = screen_text(text, section_key="rm_input")

    unmappable = False
    if expect_product_reference and text.strip():
        vocabulary = get_vocabulary()
        unmappable = not vocabulary.maps_to_approved_structure(text)

    return InputScreenResult(findings=findings, unmappable_product=unmappable)


def screen_version(
    db: Session,
    version: DocumentVersion,
    *,
    include_decisioning: bool = False,
) -> ScreeningResult:
    """Screen a persisted version and record the result.

    Runs before display on every version, including versions created by an RM edit —
    an edit can introduce prohibited terminology just as a generation can.
    """
    vocabulary = get_vocabulary()

    findings = screen_sections(
        {s.section_key: s.content for s in version.sections},
        vocabulary=vocabulary,
        include_decisioning=include_decisioning,
    )

    if has_blocking_findings(findings):
        outcome = ScreeningOutcome.BLOCKED
    elif findings:
        outcome = ScreeningOutcome.FLAGGED
    else:
        outcome = ScreeningOutcome.PASS

    result = ScreeningResult(
        version_id=version.id,
        layer=ScreeningLayer.DETERMINISTIC,
        outcome=outcome,
        findings=[f.to_dict() for f in findings],
        vocabulary_version=vocabulary.version,
    )
    db.add(result)
    db.flush()

    return result


def record_semantic_findings(
    db: Session,
    version: DocumentVersion,
    findings: list[dict],
) -> ScreeningResult:
    """Record advisory semantic findings.

    The outcome is `FLAGGED` or `PASS` — never `BLOCKED`. The semantic layer can only
    add findings; the authority to block belongs to the deterministic gate alone
    (research.md R5). There is deliberately no branch here that produces `BLOCKED`.
    """
    result = ScreeningResult(
        version_id=version.id,
        layer=ScreeningLayer.SEMANTIC,
        outcome=ScreeningOutcome.FLAGGED if findings else ScreeningOutcome.PASS,
        findings=findings,
        vocabulary_version=get_vocabulary().version,
    )
    db.add(result)
    db.flush()

    return result
