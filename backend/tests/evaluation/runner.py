"""Evaluation harness runner (tasks T113, T120).

Runs every case through the real pipeline stages and applies the gates.

Two modes:

  **Deterministic** (default) — cases run against scripted compositions defined in
  `simulated.py`. This exercises the validation, screening, and gap machinery on known
  inputs, so the gates are enforced in CI on every commit at zero cost. It cannot tell
  you how the model behaves.

  **Live** (`--run-model`) — the same cases run against `AnthropicAdapter`. This is the
  only mode that measures the actual model, and it is what the recorded baseline in
  `BASELINE.md` must come from.

Both modes apply identical gates. That is the point: the deterministic mode proves the
*harness* is correct and the guards fire, and the live mode then measures the system
that ships.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.documents.validators import SectionDraft
from tests.evaluation.cases import ALL_CASES, EvaluationCase
from tests.evaluation.gates import GateReport, evaluate_gates
from tests.evaluation.metrics.fabrication import FabricationResult, measure_fabrication
from tests.evaluation.metrics.grounding import (
    CitationResult,
    GapResult,
    InjectionResult,
    measure_citations,
    measure_gaps,
    measure_injection,
)
from tests.evaluation.metrics.screening import ScreeningResult, measure_screening


@dataclass
class CaseOutcome:
    """What one case produced."""

    case: EvaluationCase
    sections: list[SectionDraft]
    claims: list
    was_blocked: bool
    generation_refused: bool = False
    error: str | None = None

    # How many sections the model returned with content but no citation, which
    # production validation then converted to gaps. `sections` above is the validated
    # result — what an RM would actually receive — so this is recorded separately to
    # keep the model's raw behaviour visible rather than silently corrected away.
    uncited_by_model: int = 0


@dataclass
class EvaluationRun:
    mode: str
    outcomes: list[CaseOutcome] = field(default_factory=list)

    fabrication: FabricationResult = field(default_factory=FabricationResult)
    citations: CitationResult = field(default_factory=CitationResult)
    gaps: GapResult = field(default_factory=GapResult)
    screening: ScreeningResult = field(default_factory=ScreeningResult)
    injection: InjectionResult = field(default_factory=InjectionResult)

    def gate_report(self) -> GateReport:
        return evaluate_gates(
            fabrication=self.fabrication,
            citations=self.citations,
            gaps=self.gaps,
            screening=self.screening,
            injection=self.injection,
        )


def measure(run: EvaluationRun, outcome: CaseOutcome) -> None:
    """Apply every applicable metric to one case outcome.

    A refused generation is measured for screening only. There is no output to check
    for fabricated figures — which is exactly the fail-closed behaviour working, not a
    case being skipped.
    """
    case = outcome.case

    measure_screening(case, outcome.sections, outcome.was_blocked, run.screening)

    if outcome.was_blocked or outcome.generation_refused:
        return

    measure_fabrication(case, outcome.sections, outcome.claims, run.fabrication)
    measure_citations(case, outcome.sections, outcome.claims, run.citations)
    measure_gaps(case, outcome.sections, run.gaps)

    if case.family.value == "adversarial":
        measure_injection(case, outcome.sections, run.injection)


def run_evaluation(
    execute,
    *,
    mode: str,
    cases: list[EvaluationCase] | None = None,
) -> EvaluationRun:
    """Run every case through `execute` and apply the gates.

    `execute` takes an EvaluationCase and returns a CaseOutcome. The deterministic and
    live modes differ only in that function, so the two modes cannot drift apart in how
    they measure.
    """
    run = EvaluationRun(mode=mode)

    for case in cases if cases is not None else ALL_CASES:
        outcome = execute(case)
        run.outcomes.append(outcome)
        measure(run, outcome)

    return run


def _uncited_note(run: EvaluationRun) -> str:
    """Report what validation had to correct, so a passing gate is not mistaken for a
    perfect model.

    Citation resolution is measured on validated output — what an RM actually receives.
    Without this line, a model that wrote uncited prose in every section would score
    100% and look flawless, because production converted each one to a gap. The gate is
    about delivery; this number is about the model.
    """
    total = sum(o.uncited_by_model for o in run.outcomes)
    if not total:
        return "  model wrote no uncited content — nothing for validation to correct"
    return (
        f"  note: the model returned {total} section(s) with content but no citation; "
        "validation converted each to a gap before it could reach an RM"
    )


def render_report(run: EvaluationRun) -> str:
    """Full report: per-metric summary, gates, and per-case detail."""
    lines = [
        f"Warba Bank — Grounding Evaluation ({run.mode} mode)",
        "=" * 72,
        "",
        run.fabrication.summary(),
        run.citations.summary(),
        _uncited_note(run),
        run.gaps.summary(),
        run.screening.summary(),
        run.injection.summary(),
        "",
        run.gate_report().render(),
        "",
        "PER-CASE OUTCOMES",
        "-" * 72,
    ]

    for outcome in run.outcomes:
        status = (
            "refused"
            if outcome.generation_refused
            else "blocked"
            if outcome.was_blocked
            else "produced"
        )
        gap_count = sum(len(s.gaps) for s in outcome.sections)
        lines.append(
            f"  {outcome.case.case_id:<10} {outcome.case.family.value:<12} "
            f"{status:<9} sections={len(outcome.sections)} gaps={gap_count}"
        )
        if outcome.error:
            lines.append(f"             error: {outcome.error}")

    return "\n".join(lines)
