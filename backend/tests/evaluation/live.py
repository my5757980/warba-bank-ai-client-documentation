"""Live executor — runs evaluation cases against the real model (task T122).

This is the only mode that measures what actually ships. The deterministic mode proves
the harness is correct; this proves the *system* is.

It drives the real `AnthropicAdapter` through both passes and then applies the same
production validation and screening the API uses. Nothing is stubbed except the
database, which is bypassed: we measure the generation pipeline, not persistence.
"""

from __future__ import annotations

import logging

from app.documents.templates import load_template_file
from app.documents.validators import SectionDraft
from app.ports.types import GenerationError, GenerationRequest, GroundingScope, Source
from app.screening.deterministic import has_blocking_findings, screen_text
from app.screening.vocabulary import get_vocabulary
from tests.evaluation.cases import EvaluationCase
from tests.evaluation.runner import CaseOutcome

logger = logging.getLogger(__name__)

_TEMPLATE_CACHE: dict[str, dict] = {}


def _template(document_type: str) -> dict:
    if document_type not in _TEMPLATE_CACHE:
        from pathlib import Path

        name = document_type.lower() + ".yaml"
        path = Path(__file__).resolve().parents[2] / "config" / "templates" / name
        _TEMPLATE_CACHE[document_type] = load_template_file(path)
    return _TEMPLATE_CACHE[document_type]


def _schema(document_type: str):
    from app.documents.templates import schema_for
    from app.enums import DocumentType

    return schema_for(DocumentType(document_type))


def execute_live_case(case: EvaluationCase, adapter) -> CaseOutcome:
    """Run one case through the real two-pass pipeline.

    Mirrors `GenerationService.generate` exactly: input screen → ground → compose →
    convert to drafts → output screen. Validation is applied by the metrics themselves,
    so a fabricated figure is *measured* here rather than raising, which is what lets
    the harness report a count instead of just failing on the first bad case.
    """
    vocabulary = get_vocabulary()
    template = _template(case.document_type)

    # 1. Input screen (FR-017) — a non-compliant request is refused before drafting.
    if has_blocking_findings(screen_text(case.meeting_notes, section_key="rm_input")):
        return CaseOutcome(
            case=case, sections=[], claims=[], was_blocked=True, generation_refused=True
        )

    sources = [
        Source(
            source_id="meeting_notes",
            kind="MEETING_NOTES",
            label="Meeting notes (RM supplied)",
            content=case.meeting_notes,
        )
    ]

    request = GenerationRequest(
        document_id=__import__("uuid").uuid4(),
        document_type=case.document_type,
        client_reference=case.case_id,
        sources=sources,
        scope=GroundingScope(
            document_type=case.document_type,
            client_reference=case.case_id,
            section_titles=[s["title"] for s in template["sections"]],
        ),
    )

    # 2. Pass A — Grounding.
    try:
        ledger = adapter.ground(request)
    except GenerationError as exc:
        return CaseOutcome(
            case=case,
            sections=[],
            claims=[],
            was_blocked=False,
            generation_refused=True,
            error=f"grounding: {exc}",
        )

    # 3. Pass B — Composition. The ledger is the only factual input.
    try:
        composed = adapter.compose(
            ledger,
            schema=_schema(case.document_type),
            template_guidance=_guidance(template),
            approved_terminology=vocabulary.approved_terminology,
        )
    except GenerationError as exc:
        return CaseOutcome(
            case=case,
            sections=[],
            claims=ledger.claims,
            was_blocked=False,
            generation_refused=True,
            error=f"composition: {exc}",
        )

    sections = _to_drafts(composed, template)

    # 4. Output screen — the binding gate before anything reaches an RM (FR-015).
    findings = [
        f for s in sections if s.content for f in screen_text(s.content, section_key=s.section_key)
    ]
    blocked = has_blocking_findings(findings)

    logger.info(
        "live_case_complete",
        extra={
            "case_id": case.case_id,
            "claim_count": len(ledger.claims),
            "section_count": len(sections),
            "blocked": blocked,
        },
    )

    return CaseOutcome(
        case=case,
        sections=[] if blocked else sections,
        claims=ledger.claims,
        was_blocked=blocked,
        generation_refused=blocked,
    )


def _guidance(template: dict) -> str:
    lines = [f"Draft a {template['display_name']} with these sections:\n"]
    for definition in template["sections"]:
        lines.append(f"- {definition['title']} (key: {definition['key']})")
        if definition.get("guidance"):
            lines.append(f"  {definition['guidance'].strip()}")
    return "\n".join(lines)


def _to_drafts(composed, template: dict) -> list[SectionDraft]:
    drafts: list[SectionDraft] = []
    for ordinal, definition in enumerate(template["sections"]):
        section = getattr(composed, definition["key"], None)
        if section is None:
            continue
        drafts.append(
            SectionDraft(
                section_key=definition["key"],
                title=definition["title"],
                ordinal=ordinal,
                content=getattr(section, "content", None),
                evidence_refs=list(getattr(section, "evidence_refs", []) or []),
                gaps=[
                    g if isinstance(g, dict) else g.model_dump()
                    for g in (getattr(section, "gaps", []) or [])
                ],
                confidence=str(getattr(section, "confidence", "MEDIUM")),
                contains_external_data=bool(getattr(section, "contains_external_data", False)),
            )
        )
    return drafts
