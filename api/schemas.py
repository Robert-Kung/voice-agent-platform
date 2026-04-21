"""Pydantic schemas for API request/response bodies."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Profile ──────────────────────────────────────────────────


class ProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = ""
    description: str = ""
    is_active: bool = True


class ProfileCreate(ProfileBase):
    config: dict[str, Any] = Field(default_factory=dict)


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    config: dict[str, Any] | None = None


class ProfileOut(ProfileBase):
    id: str
    config: dict[str, Any]
    is_dirty: bool = True
    is_live: bool = False
    last_deployed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Session ──────────────────────────────────────────────────


class SessionSummary(BaseModel):
    id: str
    room_name: str
    profile_id: str | None
    participant_identity: str
    started_at: datetime
    ended_at: datetime | None
    status: str
    shutdown_reason: str
    duration_seconds: float | None
    total_cost_usd: float | None

    model_config = ConfigDict(from_attributes=True)


class SessionDetail(SessionSummary):
    raw_report: dict[str, Any] = Field(default_factory=dict)


class SessionEventOut(BaseModel):
    id: int
    seq: int
    event_type: str
    timestamp: datetime
    payload: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


# ── Stats ────────────────────────────────────────────────────


class ProfileStatsOut(BaseModel):
    profile_id: str | None
    profile_name: str | None
    session_count: int
    total_duration_seconds: float
    total_cost_usd: float
    avg_duration_seconds: float


class DailyStatsOut(BaseModel):
    date: str  # YYYY-MM-DD
    session_count: int
    total_duration_seconds: float
    total_cost_usd: float
