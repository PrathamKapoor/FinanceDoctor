"""SQLAlchemy engine and session setup."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    kwargs: dict[str, object] = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), future=True, expire_on_commit=False)
    return _session_factory


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped database session."""
    factory = get_session_factory()
    with factory() as session:
        yield session


def create_schema(engine: Engine | None = None) -> None:
    """Create all tables (idempotent)."""
    Base.metadata.create_all(engine or get_engine())


def drop_schema(engine: Engine | None = None) -> None:
    """Drop all tables."""
    Base.metadata.drop_all(engine or get_engine())