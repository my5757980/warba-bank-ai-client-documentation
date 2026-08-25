"""Shared API dependencies."""

from __future__ import annotations

from app.ports.generation_port import GenerationPort


# Not cached: a failed construction (missing credential) must not be memoised, or the
# service would stay broken for the life of the process after credentials are fixed.
def _adapter() -> GenerationPort:
    """Build the Anthropic adapter lazily.

    Imported inside the function so the vendor SDK is only loaded when generation is
    actually used. Tests override `get_generation_port` with the stub and never reach
    this path.
    """
    from app.adapters.anthropic_adapter import AnthropicAdapter

    return AnthropicAdapter()


def get_generation_port() -> GenerationPort:
    """FastAPI dependency for the generation port.

    Route handlers depend on the *protocol*, so `app.dependency_overrides` can swap in
    `StubGenerationPort` for tests without touching a line of application code — the
    practical payoff of the port abstraction (NFR-SCA-04).
    """
    return _adapter()
