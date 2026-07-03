"""Profile text test run store operations."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session as DbSession

from db.event_sanitizer import sanitize_event_payload
from db.models import Profile, ProfileTestRun, ProfileTestRunEvent

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
VALID_STATUSES = {"created", "running", *TERMINAL_STATUSES}
VALID_TOOL_MODES = {"dry_run", "live"}
VALID_RUN_KINDS = {"flow", "llm_text"}


def profile_config_hash(config_json: str | dict[str, Any] | None) -> str:
    """Stable SHA-256 hash for profile config snapshots."""
    if isinstance(config_json, dict):
        text = json.dumps(config_json, ensure_ascii=False, sort_keys=True)
    else:
        text = config_json or "{}"
        try:
            parsed = json.loads(text)
            text = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        except (json.JSONDecodeError, TypeError):
            pass
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create_run(
    db: DbSession,
    *,
    profile: Profile,
    user_message: str,
    tool_execution_mode: str = "dry_run",
    status: str = "created",
    kind: str = "flow",
    user_messages: list[str] | None = None,
) -> ProfileTestRun:
    """Create a profile-scoped test run (flow or llm_text)."""
    if tool_execution_mode not in VALID_TOOL_MODES:
        raise ValueError(f"invalid tool execution mode: {tool_execution_mode}")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid run status: {status}")
    if kind not in VALID_RUN_KINDS:
        raise ValueError(f"invalid run kind: {kind}")

    run = ProfileTestRun(
        profile_id=profile.id,
        profile_config_hash=profile_config_hash(profile.config_json),
        profile_snapshot_at=profile.updated_at or datetime.now(timezone.utc),
        status=status,
        kind=kind,
        tool_execution_mode=tool_execution_mode,
        user_message=user_message,
        user_messages_json=(
            json.dumps(user_messages, ensure_ascii=False) if user_messages is not None else None
        ),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def append_event(
    db: DbSession,
    run_id: str,
    *,
    event_type: str,
    payload: dict[str, Any] | None = None,
    severity: str = "info",
    timestamp: datetime | None = None,
) -> ProfileTestRunEvent:
    """Append one ordered sanitized event to a test run and commit it."""
    next_seq = next_event_seq(db, run_id)
    event = ProfileTestRunEvent(
        run_id=run_id,
        seq=next_seq,
        event_type=event_type,
        severity=severity,
        timestamp=timestamp or datetime.now(timezone.utc),
        payload_json=json.dumps(sanitize_event_payload(payload), ensure_ascii=False),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def append_events(
    db: DbSession,
    run_id: str,
    events: list[dict[str, Any]],
) -> int:
    """Append several events in order and commit once."""
    seq = next_event_seq(db, run_id)
    rows: list[ProfileTestRunEvent] = []
    for item in events:
        rows.append(
            ProfileTestRunEvent(
                run_id=run_id,
                seq=seq,
                event_type=item["event_type"],
                severity=item.get("severity", "info"),
                timestamp=item.get("timestamp", datetime.now(timezone.utc)),
                payload_json=json.dumps(
                    sanitize_event_payload(item.get("payload") or item.get("payload_json")),
                    ensure_ascii=False,
                ),
            )
        )
        seq += 1
    db.add_all(rows)
    db.commit()
    return len(rows)


def next_event_seq(db: DbSession, run_id: str) -> int:
    last = (
        db.query(ProfileTestRunEvent)
        .filter(ProfileTestRunEvent.run_id == run_id)
        .order_by(desc(ProfileTestRunEvent.seq))
        .first()
    )
    return 1 if last is None else last.seq + 1


def finalize_run(
    db: DbSession,
    run_id: str,
    *,
    status: str,
    final_summary: dict[str, Any] | None = None,
) -> ProfileTestRun | None:
    """Set a terminal status and optional summary."""
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"invalid terminal status: {status}")
    run = db.get(ProfileTestRun, run_id)
    if run is None:
        return None
    run.status = status
    run.completed_at = datetime.now(timezone.utc)
    run.updated_at = run.completed_at
    if final_summary is not None:
        run.final_summary_json = json.dumps(sanitize_event_payload(final_summary), ensure_ascii=False)
    db.commit()
    db.refresh(run)
    return run


def update_run_status(db: DbSession, run_id: str, status: str) -> ProfileTestRun | None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid run status: {status}")
    run = db.get(ProfileTestRun, run_id)
    if run is None:
        return None
    run.status = status
    run.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: DbSession, run_id: str) -> ProfileTestRun | None:
    return db.get(ProfileTestRun, run_id)


def get_run_for_profile(db: DbSession, *, profile_id: str, run_id: str) -> ProfileTestRun | None:
    return (
        db.query(ProfileTestRun)
        .filter(ProfileTestRun.profile_id == profile_id)
        .filter(ProfileTestRun.id == run_id)
        .first()
    )


def get_events(db: DbSession, run_id: str) -> list[ProfileTestRunEvent]:
    return (
        db.query(ProfileTestRunEvent)
        .filter(ProfileTestRunEvent.run_id == run_id)
        .order_by(ProfileTestRunEvent.seq)
        .all()
    )


def list_runs(
    db: DbSession,
    *,
    profile_id: str,
    limit: int = 50,
    offset: int = 0,
    kind: str | None = None,
) -> list[ProfileTestRun]:
    query = db.query(ProfileTestRun).filter(ProfileTestRun.profile_id == profile_id)
    if kind is not None:
        query = query.filter(ProfileTestRun.kind == kind)
    return (
        query.order_by(desc(ProfileTestRun.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_runs(db: DbSession, *, profile_id: str, kind: str | None = None) -> int:
    query = db.query(ProfileTestRun).filter(ProfileTestRun.profile_id == profile_id)
    if kind is not None:
        query = query.filter(ProfileTestRun.kind == kind)
    return query.count()


def parse_summary(run: ProfileTestRun) -> dict[str, Any]:
    try:
        return json.loads(run.final_summary_json) if run.final_summary_json else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def parse_user_messages(run: ProfileTestRun) -> list[str]:
    """Full ordered user message list; falls back to the legacy single message."""
    if run.user_messages_json:
        try:
            parsed = json.loads(run.user_messages_json)
            if isinstance(parsed, list):
                return [str(m) for m in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
    return [run.user_message] if run.user_message else []


def parse_event_payload(event: ProfileTestRunEvent) -> dict[str, Any]:
    try:
        payload = json.loads(event.payload_json) if event.payload_json else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return sanitize_event_payload(payload)
