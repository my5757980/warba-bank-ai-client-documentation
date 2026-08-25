"""Database engine, session factory, and the declarative base.

The engine is created lazily rather than at import time. Eager creation would mean
importing any ORM model — or any module that merely references one — requires a
working database driver, which couples pure unit tests (screening, validators, hash
chain) to infrastructure they do not use.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


@lru_cache
def get_engine() -> Engine:
    """The process-wide engine, built on first use."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        echo=False,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
