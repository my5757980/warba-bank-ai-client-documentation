"""Prohibited terminology metric (task T117) — SC-007.

Gate: **zero** prohibited terms in any draft presented to an RM.

The measurement point matters. Terminology appearing in the *input* is expected — a
client can ask for whatever they like. What must never happen is a draft containing
prohibited terminology reaching a Relationship Manager as though it were valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.documents.validators import SectionDraft
from app.screening.deterministic import has_blocking_findings, screen_sections
from tests.evaluation.cases import EvaluationCase


@dataclass
class ScreeningResult:
    cases_run: int = 0
    terms_reaching_rm: list[str] = field(default_factory=list)
    correct_blocks: int = 0
    missed_blocks: list[str] = field(default_factory=list)
    false_blocks: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.terms_reaching_rm and not self.missed_blocks and not self.false_blocks

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"Prohibited terminology: {len(self.terms_reaching_rm)} reached an RM "
            f"(gate: 0) — {verdict}\n"
            f"  correct blocks: {self.correct_blocks}, "
            f"missed: {len(self.missed_blocks)}, false: {len(self.false_blocks)}"
        )


def measure_screening(
    case: EvaluationCase,
    sections: list[SectionDraft],
    was_blocked: bool,
    result: ScreeningResult | None = None,
) -> ScreeningResult:
    """Measure screening behaviour for one case.

    Three distinct failures, each reported separately because they have different
    causes and different fixes:

      * a prohibited term reaching an RM — the gate did not fire
      * a missed block — a case that should have been refused was not
      * a false block — compliant content refused, which is how a gate loses its
        credibility with the people who rely on it
    """
    result = result or ScreeningResult()
    result.cases_run += 1

    findings = screen_sections({s.section_key: s.content for s in sections})
    blocking = has_blocking_findings(findings)

    if case.expect_screening_block:
        if was_blocked or blocking:
            result.correct_blocks += 1
        else:
            result.missed_blocks.append(
                f"{case.case_id}: expected a screening block, draft was allowed through"
            )
    elif was_blocked or blocking:
        result.false_blocks.append(
            f"{case.case_id}: compliant content was blocked — "
            f"terms: {[f.term for f in findings if f.blocks]}"
        )

    # If a draft was correctly refused, nothing reached the RM and there is nothing
    # further to measure. Only content that was actually displayed counts here.
    if not was_blocked:
        for finding in findings:
            if finding.blocks:
                result.terms_reaching_rm.append(
                    f"{case.case_id} · {finding.section_key}: {finding.term!r} "
                    f"({finding.rule_id}) reached the RM"
                )

    return result
