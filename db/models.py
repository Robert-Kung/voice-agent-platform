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
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    sessions: Mapped[list["Session"]] = relationship(back_populates="profile")


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
