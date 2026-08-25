"""Call report structured-output schema — DT1 (task T088).

Field names match `config/templates/call_report.yaml` section keys exactly. The
generation service reads sections off this object by key, so a mismatch between the
two would silently drop a section — which coverage validation then catches as a
missing required section rather than letting it pass unnoticed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.documents.schemas.base import Section


class CallReportSections(BaseModel):
    """A complete client call report.

    Every section is required at the schema level, so the model must produce all eight
    even when the notes support only some. A section it cannot support arrives with
    `content: null` and a populated `gaps` list — which is exactly the honest outcome,
    and is why no field here is optional.
    """

    meeting_metadata: Section = Field(
        description="Client, date, attendees, and channel — only as stated in the notes."
    )
    purpose: Section = Field(
        description="Why the meeting was held. Do not infer a purpose from the content."
    )
    discussion_summary: Section = Field(
        description=(
            "Professional narrative of the discussion in the order raised. Convert "
            "fragments to full sentences without adding facts."
        )
    )
    client_requirements: Section = Field(
        description="What the client asked for, with amounts and timelines only where stated."
    )
    products_discussed: Section = Field(
        description=(
            "Islamic products and structures referenced, using approved terminology. "
            "Flag anything that maps to no approved structure rather than naming one."
        )
    )
    risks_and_concerns: Section = Field(
        description=(
            "Risks, concerns, or adverse signals raised. Do not soften these. If none "
            "were raised, state that explicitly."
        )
    )
    action_items: Section = Field(
        description=(
            "Agreed actions with owner and target date. Where no date was agreed, "
            "record a gap rather than proposing one."
        )
    )
    next_steps: Section = Field(
        description=(
            "Agreed next contact and follow-up date. If no follow-up date was agreed, "
            "this MUST be a gap. Never propose a date."
        )
    )
