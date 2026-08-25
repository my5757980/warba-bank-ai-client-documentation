"""Deterministic stub implementing GenerationPort (task T053).

Every integration test runs against this. No model calls, no network, no cost, and
identical results on every run — so a failing integration test means the *pipeline* is
broken, never that the model had an off day.

The stub is deliberately literal-minded: it returns exactly the ledger and composition
it is handed. That lets a test construct the precise adversarial case it needs — an
unresolvable evidence ref, a fabricated figure, an injected instruction — and assert
that the validation layer catches it. The stub is not trying to be a good model; it is
trying to be a controllable one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.ports.types import (
    Claim,
    GenerationError,
    GenerationRequest,
    Ledger,
    ScreeningFinding,
)


@dataclass
class StubGenerationPort:
    """A scripted GenerationPort.

    Attributes:
        ledger: returned by `ground()`.
        composition: returned by `compose()`.
        semantic_findings: returned by `screen_semantic()`.
        fail_on: stage name that should raise, for fail-closed tests.
    """

    ledger: Ledger = field(default_factory=Ledger)
    composition: BaseModel | None = None
    semantic_findings: list[ScreeningFinding] = field(default_factory=list)
    fail_on: str | None = None

    # Recorded for assertions.
    ground_calls: list[GenerationRequest] = field(default_factory=list)
    compose_calls: list[dict[str, Any]] = field(default_factory=list)

    def ground(self, request: GenerationRequest) -> Ledger:
        self.ground_calls.append(request)
        if self.fail_on == "grounding":
            raise GenerationError("stubbed grounding failure", stage="grounding")
        return self.ledger

    def compose(
        self,
        ledger: Ledger,
        *,
        schema: type[BaseModel],
        template_guidance: str,
        approved_terminology: dict[str, str],
        rm_instruction: str | None = None,
    ) -> BaseModel:
        # Recorded so a test can assert what the composing call actually received —
        # in particular, that it received a ledger and nothing resembling a raw source.
        self.compose_calls.append(
            {
                "ledger": ledger,
                "schema": schema,
                "template_guidance": template_guidance,
                "rm_instruction": rm_instruction,
            }
        )
        if self.fail_on == "composition":
            raise GenerationError("stubbed composition failure", stage="composition")
        if self.composition is None:
            raise GenerationError("stub has no composition configured", stage="composition")
        return self.composition

    def screen_semantic(
        self,
        sections: dict[str, str | None],
        *,
        approved_structures: list[str],
    ) -> list[ScreeningFinding]:
        return self.semantic_findings


def claim(
    claim_id: str,
    text: str,
    *,
    excerpt: str | None = None,
    source_label: str = "Synthetic Source",
    page: int | None = None,
    is_external: bool = False,
) -> Claim:
    """Build a ledger claim for a test fixture."""
    return Claim(
        claim_id=claim_id,
        claim_text=text,
        source_type="CLIENT_RECORD",
        source_id=None,
        source_label=source_label,
        verbatim_excerpt=excerpt if excerpt is not None else text,
        locator={"page_start": page, "page_end": page} if page else {},
        is_external=is_external,
    )


def ledger(*claims: Claim, model_id: str = "stub-model") -> Ledger:
    """Build a ledger from claims."""
    return Ledger(
        claims=list(claims),
        model_id=model_id,
        source_manifest={"offered": len(claims), "source_ids": []},
    )
