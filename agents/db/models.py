"""SQLAlchemy models for agent management platform."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # True when DB config has edits not yet exported to YAML on disk. If True,
    # the Cloud image's baked-in YAML is stale for this profile and a full
    # `lk agent deploy` is required before switching to it.
    is_dirty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # True when this profile is the one AGENT_PROFILE currently points to on Cloud.
    # Exactly one row should have is_live=True after the first successful activation;
    # the admin UI is the sole writer (if someone flips AGENT_PROFILE via `lk` CLI
    # directly, DB will go stale until next admin-UI action).
    is_live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_deployed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    sessions: Mapped[list["Session"]] = relationship(back_populates="profile")
    test_runs: Mapped[list["ProfileTestRun"]] = relationship(back_populates="profile")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    room_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    profile_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("profiles.id"), nullable=True)
    participant_identity: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    shutdown_reason: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_report_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # "realtime" or "pipeline" — captured from AGENT_MODE env at session start.
    # Nullable for rows written before this column existed.
    agent_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # JSON of the resolved model names at session start, as segment lists (2.5a):
    # {"schema": 1, "llm": [{"model": "google/gemini-3.1-flash-lite"}], "stt": [...],
    # "tts": [...]} or {"schema": 1, "realtime": [{"model": "..."}], "stt": [...]}.
    # Lists so graph per-node models can record several segments per kind later.
    # Cost prices by segment [0] instead of the metrics-reported name, which is
    # "FallbackAdapter" for any fallback chain (see db/cost.py). Nullable for rows
    # written before this column; cost also accepts the pre-2.5a flat shape.
    model_names_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    profile: Mapped[Profile | None] = relationship(back_populates="sessions")
    events: Mapped[list["SessionEvent"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class SessionEvent(Base):
    __tablename__ = "session_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    session: Mapped[Session] = relationship(back_populates="events")


class ProfileTestRun(Base):
    __tablename__ = "profile_test_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("profiles.id"), nullable=False, index=True)
    profile_config_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    profile_snapshot_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created")
    # "flow" (deterministic wiring smoke, no LLM) or "llm_text" (LLM-backed text test).
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="flow")
    tool_execution_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="dry_run")
    user_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # JSON array of user messages for multi-turn llm_text runs; NULL for legacy
    # single-message rows. user_message keeps the first message for compatibility.
    user_messages_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    profile: Mapped[Profile] = relationship(back_populates="test_runs")
    events: Mapped[list["ProfileTestRunEvent"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class ProfileTestRunEvent(Base):
    __tablename__ = "profile_test_run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("profile_test_runs.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    run: Mapped[ProfileTestRun] = relationship(back_populates="events")
