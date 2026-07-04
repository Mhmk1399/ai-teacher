"""Shared pytest fixtures.

Every test runs against a throwaway in-memory SQLite database created from the
ORM metadata, so tests never touch the developer's real ``data/lingua.db`` and
never require Ollama. AI is always exercised through fake providers.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.models import Base
import core.competency.models  # noqa: F401  (register competency tables on Base)


@pytest.fixture()
def engine():
    """A fresh in-memory database with the full schema, per test."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture()
def db(engine) -> Session:
    """A session bound to the in-memory engine."""
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = factory()
    try:
        yield s
    finally:
        s.close()
