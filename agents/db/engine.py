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
        env_db_url = os.environ.get("AGENT_DB_URL", "").strip()
        if env_db_url:
            db_url = env_db_url
        else:
            db_path = os.environ.get("AGENT_DB_PATH", str(_DEFAULT_DB_PATH))
            pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{db_path}"

    if db_url.startswith("sqlite:///"):
        sqlite_path = db_url.removeprefix("sqlite:///")
        # For sqlite:///relative/path or sqlite:////absolute/path, make sure the
        # parent directory exists. Special SQLite URLs (e.g. :memory:) are skipped.
        if sqlite_path and sqlite_path != ":memory:" and not sqlite_path.startswith("file:"):
            pathlib.Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

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
    """Create all tables if they don't exist, and add any missing columns."""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


# ── Lightweight column migrations ──────────────────────────────
# SQLite supports ADD COLUMN (not DROP / RENAME easily). We only add
# columns that newer model versions introduced on top of an existing DB.

from sqlalchemy import inspect, text  # noqa: E402


def _add_missing_columns(engine: Engine) -> None:
    """Add columns present in models but missing from the live DB."""
    expected: dict[str, list[tuple[str, str]]] = {
        # table -> [(column_name, SQL type + default), ...]
        "profiles": [
            ("is_dirty", "BOOLEAN NOT NULL DEFAULT 1"),
            ("is_live", "BOOLEAN NOT NULL DEFAULT 0"),
            ("last_deployed_at", "DATETIME NULL"),
        ],
        "sessions": [
            ("agent_mode", "VARCHAR(20) NULL"),
            ("model_names_json", "TEXT NULL"),
        ],
        "profile_test_runs": [
            ("profile_config_hash", "VARCHAR(64) NOT NULL DEFAULT ''"),
            ("profile_snapshot_at", "DATETIME NULL"),
        ],
        "profile_test_run_events": [
            ("severity", "VARCHAR(20) NOT NULL DEFAULT 'info'"),
        ],
    }
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in expected.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col_name, col_def in cols:
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))


def reset_singletons() -> None:
    """Reset engine and session factory singletons (for testing)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
