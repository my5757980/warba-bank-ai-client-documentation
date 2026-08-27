"""Typed application settings.

Every value is read from the environment. Nothing is defaulted to a real credential,
and the application refuses to start if a required secret is absent — a missing secret
should be a loud startup failure, never a silent fallback to something insecure
(Constitution Principle I, research.md R14).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import MAX_UPLOAD_BYTES, MAX_UPLOAD_PAGES

_PLACEHOLDER_MARKERS = ("CHANGE_ME", "your-", "xxx", "placeholder")


class Settings(BaseSettings):
    """Application configuration, sourced entirely from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Database ---------------------------------------------------------
    database_url: str = Field(..., description="SQLAlchemy URL for the warba_app role")

    # --- Auth -------------------------------------------------------------
    jwt_secret: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 480

    # --- Model ------------------------------------------------------------
    # Which provider backs `GenerationPort`. Business logic never reads this — only
    # `app.api.deps` does, to choose an adapter. Both adapters uphold the same
    # contract; they differ in how grounding provenance is obtained (research.md R9,
    # and the Gemini adapter's module docstring).
    # "demo" is a keyless, deterministic adapter that quotes the sources literally. It
    # exists so the system can be run end to end without a credential; it is not a model
    # and produces no prose. See app/adapters/demo_adapter.py.
    model_provider: Literal["anthropic", "gemini", "demo"] = "anthropic"

    # Left as None deliberately: the Anthropic SDK resolves ANTHROPIC_API_KEY,
    # ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile on its own. Forcing a
    # value here would break the profile path.
    anthropic_api_key: str | None = None
    model_id: str = "claude-opus-5"

    gemini_api_key: str | None = None
    gemini_model_id: str = "gemini-3.6-flash"
    generation_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    generation_max_tokens: int = 64_000

    # --- Screening --------------------------------------------------------
    vocabulary_version: str = "1.0.0"

    # --- Uploads ----------------------------------------------------------
    # Anthropic Files API limits: 32 MB per request, 600 pages per PDF (research.md R8).
    # Enforced before upload so an oversized file is declined, never truncated.
    max_upload_bytes: int = MAX_UPLOAD_BYTES
    max_upload_pages: int = MAX_UPLOAD_PAGES

    # --- Environment ------------------------------------------------------
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    @field_validator("jwt_secret")
    @classmethod
    def _reject_placeholder_secret(cls, value: str) -> str:
        """Refuse to boot on an unedited `.env.example` value.

        A placeholder secret that "works" in development is a placeholder secret that
        reaches production.
        """
        lowered = value.lower()
        if any(marker.lower() in lowered for marker in _PLACEHOLDER_MARKERS):
            raise ValueError(
                "JWT_SECRET is still a placeholder. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor.

    Cached so the values are read once at startup; a config value that changes
    mid-process would silently desynchronise audit records from behaviour.
    """
    return Settings()  # type: ignore[call-arg]
