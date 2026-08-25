"""Two-pass isolation — the architectural guarantee (research.md R3).

The accuracy guarantee rests on one property: **the Composition Pass never sees the raw
sources.** If a future change threaded sources into `compose()`, every other control in
the system would still pass while the guarantee quietly evaporated — the model could
cite a document directly and validation would have no way to tell.

These tests assert that property structurally, at the type level, so the regression is
caught by the test suite rather than by a fabricated figure in a credit memo.
"""

from __future__ import annotations

import inspect

from app.ports.generation_port import GenerationPort
from app.ports.types import Ledger, Source


class TestComposeCannotReceiveSources:
    def test_compose_signature_has_no_source_parameter(self):
        """The signature is the guarantee.

        There is no `sources` parameter on `compose`, and there must never be one.
        """
        params = set(inspect.signature(GenerationPort.compose).parameters)
        forbidden = {"sources", "source", "documents", "raw_sources", "files"}
        assert not (params & forbidden), (
            f"`compose` gained a source-bearing parameter: {params & forbidden}. "
            "The Composition Pass must only ever receive the Evidence Ledger "
            "(research.md R3)."
        )

    def test_compose_accepts_a_ledger_as_its_factual_input(self):
        params = inspect.signature(GenerationPort.compose).parameters
        assert "ledger" in params

    def test_ground_is_the_only_method_taking_sources(self):
        ground_params = inspect.signature(GenerationPort.ground).parameters
        assert "request" in ground_params

        screen_params = set(inspect.signature(GenerationPort.screen_semantic).parameters)
        assert "sources" not in screen_params


class TestLedgerIsTheOnlyFactualChannel:
    def test_rendered_ledger_contains_only_claims(self):
        from tests.support.stub_generation_port import claim
        from tests.support.stub_generation_port import ledger as make_ledger

        rendered = make_ledger(
            claim("C001", "Turnover was KWD 4,500,000.", source_label="FY2025 Statements"),
            claim("C002", "The client operates in logistics.", source_label="CRM Profile"),
        ).render_for_composition()

        assert "[C001]" in rendered
        assert "[C002]" in rendered
        assert "FY2025 Statements" in rendered

    def test_empty_ledger_says_so_explicitly(self):
        """The composing model must be told the ledger is empty, not handed silence.

        Silence invites invention; an explicit statement invites gap markers.
        """
        rendered = Ledger().render_for_composition()
        assert "No claims" in rendered

    def test_external_claims_are_marked_in_the_rendered_ledger(self):
        from tests.support.stub_generation_port import claim
        from tests.support.stub_generation_port import ledger as make_ledger

        rendered = make_ledger(
            claim("C001", "Registered in 2011.", source_label="Public Registry", is_external=True)
        ).render_for_composition()

        assert "EXTERNAL" in rendered

    def test_page_locators_reach_the_composing_model(self):
        from tests.support.stub_generation_port import claim
        from tests.support.stub_generation_port import ledger as make_ledger

        rendered = make_ledger(
            claim("C001", "Turnover was KWD 4,500,000.", source_label="Statements", page=12)
        ).render_for_composition()

        assert "p.12" in rendered


class TestSourceIntegrity:
    def test_source_requires_content_or_a_file_reference(self):
        """An empty source contributes nothing but looks like it contributed something.

        Silently including one is indistinguishable from the RM having deselected it,
        which would make the source manifest a lie.
        """
        import pytest

        with pytest.raises(ValueError, match="neither inline content nor a file"):
            Source(source_id="s1", kind="MEETING_NOTES", label="Notes")

    def test_source_with_content_is_valid(self):
        source = Source(
            source_id="s1", kind="MEETING_NOTES", label="Notes", content="Met the client."
        )
        assert source.content == "Met the client."

    def test_source_with_file_reference_is_valid(self):
        source = Source(
            source_id="s2",
            kind="UPLOADED_DOCUMENT",
            label="Statements",
            provider_file_id="file_abc123",
        )
        assert source.provider_file_id == "file_abc123"


class TestAdapterKeepsPassesSeparate:
    def test_adapter_compose_does_not_build_source_blocks(self):
        """`compose` must not call the source-block builder.

        `_build_source_blocks` is what places raw documents in a request. If it ever
        appears inside `compose`, the two passes have been merged.
        """
        source = _adapter_source("compose")
        assert "_build_source_blocks" not in source

    def test_adapter_ground_enables_citations(self):
        source = _adapter_source("_build_source_blocks")
        assert '"citations"' in source

    def test_adapter_ground_does_not_set_output_format(self):
        """Citations and structured output are mutually exclusive (400 if both)."""
        source = _adapter_source("ground")
        assert "output_format" not in source

    def test_system_prompts_contain_no_interpolation(self):
        """The instruction channel is built from constants only (research.md R7).

        An f-string in a system prompt is the shape a prompt-injection vector takes.
        """
        from app.adapters import anthropic_adapter

        for name in ("GROUNDING_SYSTEM", "COMPOSITION_SYSTEM", "SEMANTIC_SCREEN_SYSTEM"):
            prompt = getattr(anthropic_adapter, name)
            assert "{" not in prompt, (
                f"{name} contains a format placeholder. System prompts must be "
                "constants — no user or document content may be interpolated into the "
                "instruction channel."
            )


def _adapter_source(function_name: str) -> str:
    """Read one function's source without importing the anthropic SDK."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "app" / "adapters" / "anthropic_adapter.py"
    text = path.read_text(encoding="utf-8")

    marker = f"def {function_name}("
    start = text.index(marker)
    # Next def at the same indentation level ends the function body.
    rest = text[start + len(marker) :]
    end = rest.find("\n    def ")
    return rest if end == -1 else rest[:end]
