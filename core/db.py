"""Database engine, session factory, and initialization."""
from __future__ import annotations
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from core.config import settings
from core.models import Base

# SQLite needs check_same_thread=False for Streamlit's threaded model
_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    # Don't expire attributes on commit. Critical for short-lived web sessions
    # (Streamlit re-runs the script after the `with` exits; if we expire,
    # any ORM attribute read AFTER the with block raises DetachedInstanceError).
    expire_on_commit=False,
    future=True,
)


def init_db() -> None:
    """Create all tables. Safe to call multiple times."""
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Session:
    """Context manager that commits on success, rolls back on error."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session() -> Session:
    """Fresh session — caller is responsible for closing."""
    return SessionLocal()
