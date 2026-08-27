"""Shared API dependencies."""

from __future__ import annotations

from app.config import get_settings
from app.ports.generation_port import GenerationPort


# Not cached: a failed construction (missing credential) must not be memoised, or the
# service would stay broken for the life of the process after credentials are fixed.
def _adapter() -> GenerationPort:
    """Build the configured generation adapter.

    **This function is the only place in the application that knows which provider is
    in use.** Everything downstream depends on `GenerationPort`, which is what makes
    NFR-SCA-04 real rather than aspirational — swapping providers is a config change
    plus one adapter, not a rewrite.

    Imports are deferred so the vendor SDK for the *unused* provider never has to be
    installed, and so tests that override `get_generation_port` never load either.
    """
    provider = get_settings().model_provider

    if provider == "gemini":
        from app.adapters.gemini_adapter import GeminiAdapter

        return GeminiAdapter()

    from app.adapters.anthropic_adapter import AnthropicAdapter

    return AnthropicAdapter()


def get_generation_port() -> GenerationPort:
    """FastAPI dependency for the generation port.

    Route handlers depend on the *protocol*, so `app.dependency_overrides` can swap in
    `StubGenerationPort` for tests without touching a line of application code — the
    practical payoff of the port abstraction.
    """
    return _adapter()
