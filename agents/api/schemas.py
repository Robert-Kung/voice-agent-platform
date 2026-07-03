"""Pydantic schemas for API request/response bodies."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Import-light: runtime.constants pulls NO livekit plugins, so validating a
# profile's models block on save doesn't drag the agent's plugin graph (or
# require provider API keys) into the API process. Validation is shape-only —
# it never instantiates components (plan-eng-review P2 / Finding 3).
from runtime.constants import SpecError, validate_models_block


def _validate_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate the optional `models` block inside a free-form profile config.

    The rest of config stays free-form; only `models` has a known shape. Raising
    ValueError here surfaces as an HTTP 422 from the FastAPI request layer.
    """
    if config and config.get("models") is not None:
        try:
            validate_models_block(config["models"])
        except SpecError as e:
            raise ValueError(f"invalid models block: {e}") from e
    return config


# ── Profile ──────────────────────────────────────────────────


class ProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = ""
    description: str = ""
    is_active: bool = True


class ProfileCreate(ProfileBase):
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def _check_models_block(cls, v):
        return _validate_config(v)


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    config: dict[str, Any] | None = None

    @field_validator("config")
    @classmethod
    def _check_models_block(cls, v):
        return _validate_config(v)


class ProfileOut(ProfileBase):
    id: str
    config: dict[str, Any]
    is_dirty: bool = True
    is_live: bool = False
    last_deployed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Profile Test Runs ──────────────────────────────────────


class ProfileTextTestRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    tool_execution_mode: str = Field("dry_run", pattern="^(dry_run|live)$")


class ProfileTestRunSummary(BaseModel):
    id: str
    profile_id: str
    status: str
    tool_execution_mode: str
    user_message: str
    profile_config_hash: str
    profile_snapshot_at: datetime
    final_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ProfileTestRunEventOut(BaseModel):
    id: int
    seq: int
    event_type: str
    severity: str
    timestamp: datetime
    payload: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class ProfileTestRunDetail(ProfileTestRunSummary):
    events: list[ProfileTestRunEventOut] = Field(default_factory=list)


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
    agent_mode: str | None = None

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
