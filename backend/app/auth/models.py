"""User model (data-model.md §1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import UserRole


class User(Base):
    """The accountable human.

    Constitution Principle III rests on this entity being a real, named person:
    every approval records who took responsibility, and `ApprovalRecord` snapshots
    the name and role so the audit record survives later changes to this row.
    """

    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False), nullable=False
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def can_approve(self) -> bool:
        """Only an active RM may approve. Never a team lead, never an administrator."""
        return self.is_active and self.role is UserRole.RM

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email} role={self.role}>"
