"""Domain error to HTTP mapping (task T072).

Two rules govern every message produced here:

1. **Plain banking language.** The RM is not a developer. "The generation service
   returned an error" is useful; a stack trace or a model identifier is not
   (NFR-UX-02, FR-038).

2. **Never a partial document.** Every path below returns an error body and nothing
   else. There is no branch that returns a half-validated draft with a warning
   attached (FR-037).
"""

from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.documents.generation_service import ScreeningBlockedError, ValidationFailedError
from app.documents.state_machine import TransitionError
from app.ports.types import GenerationError

# Transition codes that are not simply 409.
_TRANSITION_STATUS = {
    "NOT_AN_RM": status.HTTP_403_FORBIDDEN,
    "NOT_PORTFOLIO_OWNER": status.HTTP_403_FORBIDDEN,
    "INACTIVE_ACTOR": status.HTTP_403_FORBIDDEN,
    "STALE_CONTENT_HASH": status.HTTP_412_PRECONDITION_FAILED,
    "UNRESOLVED_GAPS": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "SCREENING_BLOCKED": 451,
    "NOT_CONFIRMED": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "ALREADY_APPROVED": status.HTTP_409_CONFLICT,
}


def _body(code: str, message: str, detail: dict | None = None) -> dict:
    payload: dict = {"code": code, "message": message}
    if detail:
        payload["detail"] = detail
    return payload


async def handle_transition_error(_: Request, exc: TransitionError) -> JSONResponse:
    return JSONResponse(
        status_code=_TRANSITION_STATUS.get(exc.code, status.HTTP_409_CONFLICT),
        content=_body(exc.code, str(exc), exc.detail),
    )


async def handle_screening_blocked(_: Request, exc: ScreeningBlockedError) -> JSONResponse:
    """451 with the specific violation.

    The draft is not returned. The RM sees which term triggered the block, its rule id,
    and why — enough to correct the input, without ever being shown non-compliant
    content presented as a valid draft (FR-016).
    """
    return JSONResponse(
        status_code=451,
        content=_body(
            "SHARIAH_SCREENING_BLOCKED",
            "This draft contains terminology that is not Shariah-compliant, so it has "
            "not been produced. Review the findings below and adjust the input.",
            {
                "vocabulary_version": exc.vocabulary_version,
                "findings": [
                    {
                        "term": f.term,
                        "section_key": f.section_key,
                        "severity": f.severity,
                        "rule_id": f.rule_id,
                        "rationale": f.rationale,
                    }
                    for f in exc.findings
                    if f.blocks
                ],
            },
        ),
    )


async def handle_validation_failed(_: Request, exc: ValidationFailedError) -> JSONResponse:
    """422 when the composed document failed deterministic validation.

    The message says plainly that the system refused to show unverified content. An RM
    who sees this should understand the system caught something, not that it broke.
    """
    fatal = [
        i
        for i in exc.result.issues
        if i.code in {"UNTRACEABLE_NUMERIC", "MISSING_REQUIRED_SECTION"}
    ]

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=_body(
            "GENERATION_VALIDATION_FAILED",
            "The draft could not be verified against its sources, so it was not "
            "produced. This usually means a figure appeared that the source documents "
            "do not support. Please try again, or add the missing source.",
            {
                "issues": [
                    {"code": i.code, "section_key": i.section_key, "message": i.message}
                    for i in fatal
                ]
            },
        ),
    )


async def handle_generation_error(_: Request, exc: GenerationError) -> JSONResponse:
    """503 for a service failure. No document, partial or otherwise."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=_body(
            "GENERATION_UNAVAILABLE",
            str(exc)
            + (
                " Please try again in a moment."
                if exc.retryable
                else " Please contact support if this continues."
            ),
            {"stage": exc.stage, "retryable": exc.retryable},
        ),
    )


def register_error_handlers(app) -> None:  # type: ignore[no-untyped-def]
    app.add_exception_handler(TransitionError, handle_transition_error)
    app.add_exception_handler(ScreeningBlockedError, handle_screening_blocked)
    app.add_exception_handler(ValidationFailedError, handle_validation_failed)
    app.add_exception_handler(GenerationError, handle_generation_error)
