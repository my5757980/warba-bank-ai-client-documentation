"""Fabricated-figure metric (task T114) — the release gate behind SC-004.

**This metric reports a count, and the gate is zero.**

There is deliberately no threshold and no percentage. A threshold would license some
fabrication, and there is no defensible number of invented figures in a document that
goes into a corporate client's credit file. Either every figure traces to evidence or
the build fails.

The measurement reuses `app.documents.validators` rather than reimplementing tracing.
An evaluation harness that checked differently from production would measure a system
nobody ships.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.documents.validators import SectionDraft, extract_numerics, validate_numeric_literals
from tests.evaluation.cases import EvaluationCase


@dataclass
class FabricationFinding:
    """One figure that appears in output but in no cited evidence."""

    case_id: str
    section_key: str
    literal: str
    cited_claims: list[str]

    def __str__(self) -> str:
        return (
            f"{self.case_id} · {self.section_key}: figure {self.literal!r} "
            f"has no support in cited claims {self.cited_claims}"
        )


@dataclass
class FabricationResult:
    cases_measured: int = 0
    figures_checked: int = 0
    findings: list[FabricationFinding] = field(default_factory=list)
    forbidden_hits: list[str] = field(default_factory=list)

    @property
    def fabricated_count(self) -> int:
        """The gated number. Must be zero."""
        return len(self.findings) + len(self.forbidden_hits)

    @property
    def passed(self) -> bool:
        return self.fabricated_count == 0

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"Fabricated figures: {self.fabricated_count} (gate: 0) — {verdict}\n"
            f"  cases measured: {self.cases_measured}, figures checked: {self.figures_checked}"
        )


def measure_fabrication(
    case: EvaluationCase,
    sections: list[SectionDraft],
    claims: list,
    result: FabricationResult | None = None,
) -> FabricationResult:
    """Measure fabricated figures for one case.

    Two independent checks, because they catch different failures:

    1. **Traceability** — every numeric literal in output must appear in a claim the
       section actually cites. This is the production check, run again here.

    2. **Forbidden figures** — figures the case author knows appear in no source. This
       catches a subtler failure the first check can miss: a number that happens to be
       traceable to some claim, but is the *wrong* number for what the sentence asserts.
    """
    result = result or FabricationResult()
    result.cases_measured += 1

    for section in sections:
        if section.content:
            result.figures_checked += len(extract_numerics(section.content))

    validation = validate_numeric_literals(sections, claims)
    for issue in validation.issues:
        if issue.code == "UNTRACEABLE_NUMERIC":
            result.findings.append(
                FabricationFinding(
                    case_id=case.case_id,
                    section_key=issue.section_key,
                    literal=issue.detail.get("literal", "?"),
                    cited_claims=issue.detail.get("cited_claims", []),
                )
            )

    full_text = "\n".join(s.content or "" for s in sections)
    for forbidden in case.forbidden_figures:
        if forbidden in full_text:
            result.forbidden_hits.append(
                f"{case.case_id}: figure {forbidden!r} appears in output but is in no source"
            )

    return result
