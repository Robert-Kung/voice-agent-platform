"""FastAPI dependency injection helpers."""

from typing import Generator

from sqlalchemy.orm import Session

from db.engine import get_session_factory, init_db


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a DB session per request."""
    # Ensure tables exist (idempotent)
    init_db()
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
