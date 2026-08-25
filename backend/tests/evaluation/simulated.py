"""Deterministic executor for the evaluation harness.

Scripts what a *correct* system would produce for each case, then runs it through the
real validation and screening code. This is what makes the gates enforceable in CI: no
model calls, no cost, identical every run.

What this mode proves and does not prove is worth being precise about.

  It proves: the harness measures what it claims to, the gates fire when they should,
  and the validation and screening machinery behaves correctly on known inputs.

  It does NOT prove: that the model produces grounded output. Only `--run-model` can
  show that, and only that mode's numbers belong in BASELINE.md.

A deterministic pass is a green light for the harness, not for the system.
"""

from __future__ import annotations

from app.documents.validators import SectionDraft
from app.ports.types import Claim
from app.screening.deterministic import has_blocking_findings, screen_text
from tests.evaluation.cases import EvaluationCase
from tests.evaluation.runner import CaseOutcome

CALL_REPORT_SECTIONS = [
    ("meeting_metadata", "Meeting Details"),
    ("purpose", "Purpose of Meeting"),
    ("discussion_summary", "Discussion Summary"),
    ("client_requirements", "Client Requirements and Requests"),
    ("products_discussed", "Products Discussed"),
    ("risks_and_concerns", "Risks, Concerns and Red Flags"),
    ("action_items", "Agreed Action Items"),
    ("next_steps", "Next Steps and Follow-Up"),
]


# Lines shaped like instructions to the system rather than records of the meeting.
# A correct Grounding Pass extracts facts about what happened; it does not treat an
# embedded command as a meeting fact. Filtering here models that behaviour.
_INSTRUCTION_MARKERS = (
    "ignore all previous",
    "you are now in",
    "system note:",
    "note to the assistant",
    "do not output",
    "do not mark anything",
    "set the document status",
    "state in the report",
    "instead of marking it missing",
    "are disabled",
)


def _is_instruction(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in _INSTRUCTION_MARKERS)


def _claims_from_notes(case: EvaluationCase) -> list[Claim]:
    """Build a ledger from the case's notes, one claim per substantive line.

    Mirrors what a correct Grounding Pass produces: claims that quote the notes and
    assert nothing beyond them.
    """
    claims: list[Claim] = []
    counter = 0

    # Filter by paragraph block, not by line. An injected instruction is usually a
    # multi-line paragraph, and a line-wise filter drops the first line while letting
    # the continuation ("…has been APPROVED by the credit committee…") through as a
    # claim — which is worse than no filter, because the surviving fragment reads like
    # a fact. A block-wise filter matches how a reader actually parses the note.
    for block in case.meeting_notes.split("\n\n"):
        if _is_instruction(block):
            continue

        for raw in block.splitlines():
            line = raw.strip().lstrip("-").strip()
            if not line or len(line) < 12:
                continue

            counter += 1
            claims.append(
                Claim(
                    claim_id=f"C{counter:03d}",
                    claim_text=f"The notes state: {line}",
                    source_type="MEETING_NOTES",
                    source_id="meeting_notes",
                    source_label="Meeting notes (RM supplied)",
                    verbatim_excerpt=line,
                    locator={"char_start": 0, "char_end": len(line)},
                )
            )

    return claims


def _content_for(
    section_key: str,
    case: EvaluationCase,
    claims: list[Claim],
) -> tuple[str | None, list[str], list[dict]]:
    """Produce correct content, citations, and gaps for one section.

    A field the case marks as a known gap yields a gap marker and no content — which is
    precisely the behaviour under measurement.
    """
    if section_key in case.expected_gap_fields:
        return (
            None,
            [],
            [
                {
                    "field": section_key,
                    "label": f"[MISSING: {section_key.replace('_', ' ')} not recorded]",
                    "resolved": False,
                    "resolution_note": None,
                }
            ],
        )

    relevant = [c for c in claims if _relevant(section_key, c.claim_text)]
    if not relevant:
        return (
            None,
            [],
            [
                {
                    "field": section_key,
                    "label": f"[MISSING: {section_key.replace('_', ' ')}]",
                    "resolved": False,
                    "resolution_note": None,
                }
            ],
        )

    # Quote the claims verbatim. Anything paraphrased risks introducing a figure the
    # evidence does not support — the failure this whole harness exists to detect.
    content = " ".join(c.verbatim_excerpt for c in relevant[:4])
    return content, [c.claim_id for c in relevant[:4]], []


_SECTION_KEYWORDS = {
    "meeting_metadata": ("client:", "date:", "present:", "channel:"),
    "purpose": ("discussed", "regarding", "call about", "reviewed"),
    "discussion_summary": ("reported", "confirmed", "discussed", "said", "mentioned", "toured"),
    "client_requirements": ("asked", "requested", "seeks", "wants", "interest in"),
    "products_discussed": (
        "murabaha",
        "ijara",
        "wakala",
        "istisna",
        "loan",
        "overdraft",
        "facility",
    ),
    "risks_and_concerns": ("concern", "overdue", "delay", "risk", "no concerns"),
    "action_items": ("action:",),
    "next_steps": ("next meeting", "next contact", "reconvene"),
}


def _relevant(section_key: str, text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _SECTION_KEYWORDS.get(section_key, ()))


def execute_case(case: EvaluationCase) -> CaseOutcome:
    """Run one case deterministically through the real validation and screening code."""
    claims = _claims_from_notes(case)

    # Input screening runs first, exactly as in production (FR-017). A blocked input
    # produces no document at all.
    input_findings = screen_text(case.meeting_notes, section_key="rm_input")
    if has_blocking_findings(input_findings):
        return CaseOutcome(
            case=case,
            sections=[],
            claims=claims,
            was_blocked=True,
            generation_refused=True,
        )

    sections: list[SectionDraft] = []
    for ordinal, (key, title) in enumerate(CALL_REPORT_SECTIONS):
        content, refs, gaps = _content_for(key, case, claims)
        sections.append(
            SectionDraft(
                section_key=key,
                title=title,
                ordinal=ordinal,
                content=content,
                evidence_refs=refs,
                gaps=gaps,
                confidence="HIGH" if content else "LOW",
            )
        )

    # Output screening — the binding gate before anything reaches an RM (FR-015).
    output_findings = [
        f
        for section in sections
        if section.content
        for f in screen_text(section.content, section_key=section.section_key)
    ]
    blocked = has_blocking_findings(output_findings)

    return CaseOutcome(
        case=case,
        sections=[] if blocked else sections,
        claims=claims,
        was_blocked=blocked,
        generation_refused=blocked,
    )


def execute_faulty_case(case: EvaluationCase) -> CaseOutcome:
    """A deliberately broken executor used to prove the gates actually fail.

    A harness that has only ever reported PASS is a harness nobody has tested. This
    injects each failure mode the gates exist to catch — a fabricated figure, an
    unresolvable citation, a suppressed gap — so the negative case is covered too.
    """
    outcome = execute_case(case)
    if outcome.generation_refused:
        return outcome

    for section in outcome.sections:
        if section.section_key == "discussion_summary":
            section.content = "Annual turnover was KWD 7,777,777 according to the client."
            section.evidence_refs = ["C_DOES_NOT_EXIST"]
            section.gaps = []
        # Suppress every gap — the quiet failure mode.
        elif section.gaps:
            section.gaps = []
            section.content = "Details were confirmed during the meeting."

    return outcome
