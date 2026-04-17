"""FastAPI dependency injection helpers."""

from typing import Generator

from sqlalchemy.orm import Session

from db.engine import get_session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a DB session per request.

    Table creation happens once at app startup via lifespan (api/main.py),
    so we don't call init_db() here.
    """
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
