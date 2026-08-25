"""Authentication endpoints (task T074)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.security import create_access_token, verify_password
from app.config import get_settings
from app.db import get_db

router = APIRouter(tags=["Auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    team_id: uuid.UUID | None = None

    @classmethod
    def from_user(cls, user: User) -> UserResponse:
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            team_id=user.team_id,
        )


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Authenticate and issue a bearer token.

    A wrong email and a wrong password return the identical response. Distinguishing
    them would let an unauthenticated caller enumerate which staff accounts exist.
    """
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()

    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "INVALID_CREDENTIALS", "message": "Incorrect email or password."},
    )

    if user is None or not verify_password(payload.password, user.password_hash):
        raise invalid

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INACTIVE_USER", "message": "This account is not active."},
        )

    settings = get_settings()

    return LoginResponse(
        access_token=create_access_token(user.id, user.role.value),
        expires_in=settings.jwt_expiry_minutes * 60,
        user=UserResponse.from_user(user),
    )


@router.get("/auth/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.from_user(user)
