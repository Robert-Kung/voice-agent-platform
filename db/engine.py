"""Database engine and session factory."""

import os
import pathlib

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base

_DEFAULT_DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "agent_platform.db"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine(db_url: str | None = None) -> Engine:
    """Get or create the SQLAlchemy engine (singleton)."""
    global _engine
    if _engine is not None:
        return _engine

    if db_url is None:
        db_path = os.environ.get("AGENT_DB_PATH", str(_DEFAULT_DB_PATH))
        pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{db_path}"

    _engine = create_engine(db_url, echo=False)
    return _engine


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Get or create the session factory (singleton)."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory

    if engine is None:
        engine = get_engine()

    _session_factory = sessionmaker(bind=engine)
    return _session_factory


def init_db(engine: Engine | None = None) -> None:
    """Create all tables if they don't exist."""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)


def reset_singletons() -> None:
    """Reset engine and session factory singletons (for testing)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
