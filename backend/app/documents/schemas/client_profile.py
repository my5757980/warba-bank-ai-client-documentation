"""Client profile structured-output schema — DT2.

Field names match `config/templates/client_profile.yaml` section keys exactly.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.documents.schemas.base import Section


class ClientProfileSections(BaseModel):
    """A consolidated relationship brief assembled from the bank's own records.

    Every section is required. A client with thin records produces a document that is
    mostly gap markers — which is the honest and useful result, because it tells the RM
    exactly what they will need to ask for.
    """

    company_overview: Section = Field(
        description="Legal identity, registration, incorporation, and legal form."
    )
    ownership_and_management: Section = Field(
        description="Shareholding and named officers. Do not infer unrecorded roles."
    )
    business_activity: Section = Field(
        description="Sector, principal activities, locations, and headcount where recorded."
    )
    relationship_summary: Section = Field(
        description=(
            "Tenure and overall position. Report what the records show; do not "
            "characterise the relationship as strong or weak."
        )
    )
    existing_facilities: Section = Field(
        description=(
            "Each facility by approved Islamic structure with limit, utilisation, "
            "tenor, and status. Every figure must come from a cited record."
        )
    )
    financial_summary: Section = Field(
        description=(
            "Turnover, profit, and assets with fiscal year and basis. Where no "
            "statement exists this is a gap — never estimate from facility size."
        )
    )
    relationship_history: Section = Field(
        description="Notable recorded interactions in date order."
    )
    opportunities: Section = Field(
        description=(
            "Opportunities the client expressed or the records evidence. Do not "
            "generate speculative cross-sell ideas — that is the RM's judgement."
        )
    )
    risk_observations: Section = Field(
        description=(
            "Recorded risks, overdue items, KYC status, and any conflict between "
            "sources. Do not soften. No risk rating."
        )
    )
