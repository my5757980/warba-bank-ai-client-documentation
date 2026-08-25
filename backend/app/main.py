"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.config import get_settings
from app.logging import configure_logging

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="Warba Bank — AI-Powered Client Documentation",
        version="0.1.0",
        description=(
            "Drafts corporate client documentation for Relationship Managers.\n\n"
            "Three contract-level invariants:\n"
            "1. `POST /documents/{id}/approve` is the only transition into APPROVED, "
            "and it requires an authenticated RM who owns the portfolio.\n"
            "2. Generation, screening, and retrieval failures return an error and no "
            "document — never a partial draft.\n"
            "3. No endpoint mutates or deletes an audit event.\n\n"
            "All data served by this API is synthetic."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # Permissive only outside production. A prototype demo runs the frontend on a
    # different port; a real deployment must name its origins explicitly.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["ETag"],
    )

    register_error_handlers(app)

    from app.api.v1 import approval, audit, auth, documents, export, sections

    for module in (auth, documents, sections, approval, export, audit):
        app.include_router(module.router, prefix=API_PREFIX)

    @app.get("/health", tags=["Health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
