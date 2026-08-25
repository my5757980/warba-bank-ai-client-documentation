"""Authorisation dependencies (research.md R11).

Portfolio scoping lives in **one** dependency rather than being repeated per endpoint.
A rule copied into fifteen route handlers is a rule the sixteenth handler forgets, and
the sixteenth handler is the one that leaks another RM's client.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security import TokenError, decode_access_token
from app.clients.models import Client
from app.db import get_db
from app.enums import UserRole

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the bearer token.

    The user is re-read from the database on every request rather than reconstructed
    from token claims, so a deactivated account stops working immediately instead of
    at token expiry.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Please sign in."},
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": str(exc)},
        ) from exc

    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INACTIVE_USER", "message": "This account is not active."},
        )

    return user


def require_role(*roles: UserRole) -> Callable[[User], User]:
    """Restrict an endpoint to the given roles."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN_ROLE",
                    "message": "You do not have permission to perform this action.",
                },
            )
        return user

    return dependency


def visible_client_or_404(client_id: uuid.UUID, user: User, db: Session) -> Client:
    """Fetch a client the caller is permitted to see, or 404.

    Deliberately 404, not 403. Telling an RM "this client exists but is not yours"
    confirms the existence of another RM's client, which is itself a small disclosure.

    Visibility by role:
      RM               — own portfolio only
      TEAM_LEAD        — clients owned by RMs on the same team
      COMPLIANCE       — all clients (read-only; cannot edit or approve)
      SHARIAH_REVIEWER — all clients (read-only)
    """
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Client not found."},
        )

    if user.role is UserRole.RM:
        if client.owning_rm_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Client not found."},
            )
        return client

    if user.role is UserRole.TEAM_LEAD:
        owner = db.get(User, client.owning_rm_id)
        if owner is None or owner.team_id != user.team_id or user.team_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Client not found."},
            )
        return client

    # COMPLIANCE and SHARIAH_REVIEWER read across the book. Neither can edit or
    # approve — that is enforced separately by `require_approver`.
    return client


def require_portfolio_access(
    client_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Client:
    """The single portfolio-scoping dependency. Use this on every client-scoped route."""
    return visible_client_or_404(client_id, user, db)


def require_approver(
    client_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[User, Client]:
    """Admit only the RM who owns this client's portfolio.

    Approval authority is narrower than read access on purpose. Constitution Principle
    III places accountability on the named human who owns the relationship, so a
    Compliance officer who can read every document still cannot approve one.

    The state machine re-checks all of this. That duplication is deliberate: this
    dependency produces a clean 403 at the edge, and the state machine guarantees the
    rule holds even if some future caller bypasses the dependency.
    """
    if user.role is not UserRole.RM:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "NOT_AN_RM",
                "message": "Only a Relationship Manager can approve a document.",
            },
        )

    client = db.get(Client, client_id)
    if client is None or client.owning_rm_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "NOT_PORTFOLIO_OWNER",
                "message": "You can only approve documents for clients in your own portfolio.",
            },
        )

    return user, client
