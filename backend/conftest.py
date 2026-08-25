"""Pytest bootstrap.

Loaded before any test module, which matters because `app.config` fails fast on a
missing secret and `app.db` builds an engine at import time. Setting the environment
here keeps that fail-fast behaviour intact in production while letting unit tests run
without a live database.
"""

from __future__ import annotations

import os

# Test-only values. The JWT secret is deliberately not a placeholder string, because
# `Settings` rejects placeholders — the same guard that stops an unedited .env.example
# reaching production.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://warba_app:test@localhost:5432/warba_docs_test"
)
os.environ.setdefault("JWT_SECRET", "test-only-secret-not-used-outside-the-test-suite-0123456789")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("VOCABULARY_VERSION", "1.0.0")


def pytest_addoption(parser) -> None:  # type: ignore[no-untyped-def]
    """Register `--run-model`.

    Evaluation tests make real model calls. They are opt-in so CI stays deterministic
    and free: the unit, integration, and contract suites never touch a model.
    """
    parser.addoption(
        "--run-model",
        action="store_true",
        default=False,
        help="Run evaluation tests that make real model calls.",
    )


def pytest_collection_modifyitems(config, items) -> None:  # type: ignore[no-untyped-def]
    import pytest

    if config.getoption("--run-model"):
        return

    skip = pytest.mark.skip(reason="needs --run-model (makes real model calls)")
    for item in items:
        if "model" in item.keywords:
            item.add_marker(skip)
