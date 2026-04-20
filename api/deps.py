"""FastAPI dependency injection helpers."""

import os
from typing import Generator

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
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
        db.rollback()   # Clear any uncommitted dirty state on exception paths
        db.close()


# ── Admin API key authentication ──────────────────────────────

_api_key_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


def require_admin(token: str | None = Security(_api_key_header)) -> None:
    """Verify admin API key if ADMIN_API_TOKEN env var is set.

    When ADMIN_API_TOKEN is empty or unset, authentication is skipped
    (development / local mode). When set, every protected endpoint must
    include the header ``X-Admin-Token: <token>``.
    """
    expected = os.environ.get("ADMIN_API_TOKEN", "")
    if not expected:
        return  # No token configured — skip authentication (dev mode)
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")
