"""Provider-neutral domain types for the generation port.

Nothing in this module references a vendor. These are the types business logic passes
across the port boundary, and they are what makes NFR-SCA-04 achievable: swapping
providers means writing a new adapter that speaks these types, not rewriting callers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

SourceKind = Literal["CLIENT_RECORD", "UPLOADED_DOCUMENT", "MEETING_NOTES"]


@dataclass(frozen=True)
class Source:
    """One input offered to the Grounding Pass.

    `content` carries inline text (a client record rendered as text, or pasted meeting
    notes). `provider_file_id` carries a reference to an already-uploaded document.
    Exactly one of the two is populated.

    Every source is untrusted by classification. The adapter is responsible for placing
    it in the data channel and never in the instruction channel (research.md R7).
    """

    source_id: str
    kind: SourceKind
    label: str
    content: str | None = None
    provider_file_id: str | None = None
    media_type: str | None = None
    is_external: bool = False

    def __post_init__(self) -> None:
        if not self.content and not self.provider_file_id:
            raise ValueError(
                f"Source {self.source_id!r} has neither inline content nor a file "
                "reference. An empty source would silently contribute nothing to the "
                "ledger, which is indistinguishable from a source that was excluded."
            )


@dataclass(frozen=True)
class GroundingScope:
    """What the Grounding Pass is being asked to extract.

    Scoping extraction to the sections a document actually needs keeps the ledger
    focused; an unbounded "extract everything" pass produces claims nothing cites.
    """

    document_type: str
    client_reference: str
    section_titles: list[str]
    guidance: str = ""


@dataclass
class Claim:
    """One grounded factual claim with its verbatim source span.

    `verbatim_excerpt` must be the exact text from the source. A paraphrase here would
    defeat the point: the RM inspects this to check the system's reading against the
    document, and a paraphrased excerpt cannot be checked.
    """

    claim_id: str
    claim_text: str
    source_type: SourceKind
    source_id: str | None
    source_label: str
    verbatim_excerpt: str
    locator: dict[str, Any] = field(default_factory=dict)
    is_external: bool = False

    @property
    def searchable_text(self) -> str:
        """Text searched when tracing a numeric literal back to evidence."""
        return f"{self.claim_text}\n{self.verbatim_excerpt}"


@dataclass
class Ledger:
    """The complete set of claims available to the Composition Pass.

    This is the bottleneck of the grounding architecture. The composing call receives
    this and nothing else — no raw documents — so it cannot cite what is not here.
    """

    claims: list[Claim] = field(default_factory=list)
    model_id: str = ""
    source_manifest: dict[str, Any] = field(default_factory=dict)

    def claim_ids(self) -> set[str]:
        return {c.claim_id for c in self.claims}

    def render_for_composition(self) -> str:
        """Serialise the ledger as the sole factual input to the Composition Pass.

        Rendered as an explicit, numbered list so the composing model can reference
        claims by id. Anything it writes that is not traceable to one of these lines
        will fail deterministic validation downstream.
        """
        if not self.claims:
            return "(No claims could be grounded from the supplied sources.)"

        lines = []
        for claim in self.claims:
            origin = f"{claim.source_label}"
            if claim.locator.get("page_start"):
                origin += f", p.{claim.locator['page_start']}"
            external = " [EXTERNAL — unverified]" if claim.is_external else ""
            lines.append(f"[{claim.claim_id}] {claim.claim_text} (source: {origin}){external}")
        return "\n".join(lines)


@dataclass(frozen=True)
class ScreeningFinding:
    """A finding raised by the advisory semantic screening layer.

    Advisory by construction: there is no field by which this layer can clear a
    deterministic block (research.md R5).
    """

    concern: str
    section_key: str
    severity: Literal["FLAG"]
    rationale: str


@dataclass(frozen=True)
class GenerationRequest:
    """Everything the port needs for one document generation."""

    document_id: uuid.UUID
    document_type: str
    client_reference: str
    sources: list[Source]
    scope: GroundingScope
    rm_instruction: str | None = None


class GenerationError(RuntimeError):
    """Raised when generation cannot complete.

    Callers must fail closed on this: no partial document, no unverified content
    (FR-037, NFR-SEC-07).
    """

    def __init__(self, message: str, *, stage: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.stage = stage
        self.retryable = retryable
