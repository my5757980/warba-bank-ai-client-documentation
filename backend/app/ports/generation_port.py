"""The generation port (research.md R9).

Business logic depends on this Protocol, never on a vendor SDK. The ruff banned-api
rule in `pyproject.toml` enforces that mechanically: `anthropic` is importable from
exactly one module in the codebase.

A note on the honest limit of this abstraction. The contract below is
provider-neutral — it promises a ledger of claims each bound to a verbatim excerpt and
a locator. The *mechanism* by which the current adapter produces that ledger (native
document citations) is not portable. A different provider's adapter would have to
derive locators another way and would likely produce coarser ones. What NFR-SCA-04
actually requires — that business logic never depends on a provider — holds; what it
does not promise is that every provider grounds equally well. That limitation is
recorded in plan.md under Complexity Tracking rather than hidden here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from app.ports.types import (
    GenerationRequest,
    Ledger,
    ScreeningFinding,
)


@runtime_checkable
class GenerationPort(Protocol):
    """Two-pass generation plus advisory screening.

    The two passes are separate methods rather than one `generate()` because their
    separation *is* the guarantee. `compose` receives a `Ledger` and has no parameter
    through which raw sources could reach it — the type signature makes the
    architectural rule difficult to violate by accident.
    """

    def ground(self, request: GenerationRequest) -> Ledger:
        """Pass A — extract grounded claims from the supplied sources.

        Sources are placed in the data channel with citations enabled. Returns a
        ledger in which every claim carries a verbatim excerpt and a locator pointing
        into a real source.

        An empty ledger is a valid result, not an error: a client with no records
        should produce an all-gaps document rather than invented prose.

        Raises:
            GenerationError: extraction could not complete. Callers fail closed.
        """
        ...

    def compose(
        self,
        ledger: Ledger,
        *,
        schema: type[BaseModel],
        template_guidance: str,
        approved_terminology: dict[str, str],
        rm_instruction: str | None = None,
    ) -> BaseModel:
        """Pass B — compose the document from the ledger alone.

        Note what is absent from this signature: there is no `sources` parameter. The
        composing call cannot see raw documents, which is precisely why it cannot cite
        anything that is not in the ledger.

        `schema` binds the response to a per-document-type model, so every section
        arrives with explicit `evidence_refs` and `gaps` rather than prose the caller
        would have to parse back into structure.

        `rm_instruction` is stylistic only. The adapter must scope it so it cannot
        authorise a claim, alter screening, or affect approval (research.md R7).

        Raises:
            GenerationError: composition failed or returned an unusable response.
        """
        ...

    def screen_semantic(
        self,
        sections: dict[str, str | None],
        *,
        approved_structures: list[str],
    ) -> list[ScreeningFinding]:
        """Advisory Shariah review for substance the lexicon cannot catch.

        Catches structures that are non-compliant in substance while using compliant
        vocabulary. It returns findings and nothing else — there is deliberately no
        return value by which it could clear a deterministic block (research.md R5).

        A failure here returns an empty finding list rather than raising: the binding
        gate has already run, and losing the advisory layer must not take down
        generation. This is the one place in the pipeline that degrades rather than
        fails closed, because it can only ever add findings.
        """
        ...
