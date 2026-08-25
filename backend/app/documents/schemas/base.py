"""Shared section schema (task T088).

These Pydantic models are the structured-output contract for the Composition Pass.
Their shape is what forces the model to state its evidence and its gaps explicitly
rather than writing prose a parser would have to interpret afterwards.

The design decision worth noting: `content` is Optional and `gaps` is a required list.
A model that cannot support a section has a well-typed way to say so. If the schema
demanded a non-empty string, the cheapest way to satisfy it would be to invent one —
the schema would be actively encouraging fabrication.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Gap(BaseModel):
    """Information the ledger could not support.

    A successful, expected outcome — not an error.
    """

    field: str = Field(description="Short identifier for the missing item, e.g. 'follow_up_date'.")
    label: str = Field(
        description=(
            "Human-readable marker shown to the Relationship Manager, in the form "
            "'[MISSING: audited turnover FY2025]'."
        )
    )


class Section(BaseModel):
    """One composed section of a document."""

    content: str | None = Field(
        default=None,
        description=(
            "The drafted text. Every factual statement must be supported by a claim "
            "listed in evidence_refs. Leave null if the ledger supports nothing at all "
            "for this section."
        ),
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        description=(
            "Claim identifiers from the evidence ledger that support this section, "
            "e.g. ['C001', 'C004']. Every identifier is checked against the ledger; an "
            "identifier that does not exist causes this section to be discarded."
        ),
    )
    gaps: list[Gap] = Field(
        default_factory=list,
        description=(
            "Information this section needs that the ledger does not provide. Record it "
            "here rather than estimating, inferring, or omitting it silently."
        ),
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        default="MEDIUM",
        description=(
            "HIGH when the ledger fully supports the section; MEDIUM when partially; "
            "LOW when the evidence is thin or ambiguous. An honest LOW is more useful "
            "to the reviewer than an optimistic HIGH."
        ),
    )
    contains_external_data: bool = Field(
        default=False,
        description="True if any cited claim came from an external, unverified source.",
    )
