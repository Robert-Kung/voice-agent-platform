"""Session and SessionEvent store operations."""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session as DbSession

from db.models import Session, SessionEvent


def create_session(
    db: DbSession,
    *,
    room_name: str,
    profile_id: str | None = None,
    participant_identity: str = "",
    agent_mode: str | None = None,
    model_names: dict | None = None,
) -> Session:
    """Create a new session record (status=running).

    `model_names` is the resolver's selected primary model names; stored so cost
    prices by the actual selection instead of the metrics-reported "FallbackAdapter".
    """
    sess = Session(
        room_name=room_name,
        profile_id=profile_id,
        participant_identity=participant_identity,
        status="running",
        agent_mode=agent_mode,
        model_names_json=json.dumps(model_names, ensure_ascii=False) if model_names else None,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def complete_session(
    db: DbSession,
    session_id: str,
    *,
    shutdown_reason: str = "",
    duration_seconds: float | None = None,
    total_cost_usd: float | None = None,
    raw_report_json: str | dict = "{}",
) -> Session | None:
    """Mark a session as completed with final metrics."""
    sess = db.get(Session, session_id)
    if sess is None:
        return None

    if isinstance(raw_report_json, dict):
        raw_report_json = json.dumps(raw_report_json, ensure_ascii=False)

    sess.status = "completed"
    sess.ended_at = datetime.now(timezone.utc)
    sess.shutdown_reason = shutdown_reason
    sess.duration_seconds = duration_seconds
    sess.total_cost_usd = total_cost_usd
    sess.raw_report_json = raw_report_json

    db.commit()
    db.refresh(sess)
    return sess


def fail_session(db: DbSession, session_id: str, reason: str = "") -> Session | None:
    """Mark a session as failed."""
    sess = db.get(Session, session_id)
    if sess is None:
        return None

    sess.status = "failed"
    sess.ended_at = datetime.now(timezone.utc)
    sess.shutdown_reason = reason

    db.commit()
    db.refresh(sess)
    return sess


def mark_stale_sessions(
    db: DbSession,
    *,
    max_age_hours: float = 1.0,
    reason: str = "stale (reconciled at startup)",
) -> int:
    """Mark orphaned `running` sessions (older than cutoff) as `failed`.

    Agents that crash / OOM / get killed never reach the shutdown callback,
    so their `sessions` row stays at status='running' forever. Call this at
    API startup to clean them up. Returns the number of rows reconciled.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)

    # started_at may be naive (older rows written before tz fix) — compare
    # against naive cutoff to avoid "offset-naive vs offset-aware" errors.
    cutoff_naive = cutoff.replace(tzinfo=None)

    stale = (
        db.query(Session)
        .filter(Session.status == "running")
        .filter(Session.started_at < cutoff_naive)
        .all()
    )
    for sess in stale:
        sess.status = "failed"
        sess.ended_at = now
        sess.shutdown_reason = reason

    if stale:
        db.commit()
    return len(stale)


def get_session(db: DbSession, session_id: str) -> Session | None:
    """Get a session by ID."""
    return db.get(Session, session_id)


def list_sessions(
    db: DbSession,
    *,
    profile_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Session]:
    """List sessions with optional filters."""
    q = _filtered_query(db, profile_id=profile_id, status=status)
    return q.order_by(desc(Session.started_at)).offset(offset).limit(limit).all()


def count_sessions(
    db: DbSession,
    *,
    profile_id: str | None = None,
    status: str | None = None,
) -> int:
    """Count sessions matching the same filters as list_sessions."""
    return _filtered_query(db, profile_id=profile_id, status=status).count()


def _filtered_query(
    db: DbSession,
    *,
    profile_id: str | None,
    status: str | None,
):
    q = db.query(Session)
    if profile_id is not None:
        q = q.filter(Session.profile_id == profile_id)
    if status is not None:
        q = q.filter(Session.status == status)
    return q


def add_events(
    db: DbSession,
    session_id: str,
    events: list[dict],
) -> int:
    """Batch-insert session events.

    Each event dict should have: seq, event_type, timestamp (optional), payload_json (str or dict).
    Returns the number of events inserted.
    """
    rows = []
    for ev in events:
        payload = ev.get("payload_json", "{}")
        if isinstance(payload, dict):
            payload = json.dumps(payload, ensure_ascii=False)

        rows.append(SessionEvent(
            session_id=session_id,
            seq=ev["seq"],
            event_type=ev["event_type"],
            timestamp=ev.get("timestamp", datetime.now(timezone.utc)),
            payload_json=payload,
        ))

    db.add_all(rows)
    # NOTE: no commit here — the caller is responsible for committing.
    # This allows atomic writes when combined with complete_session() in
    # a single transaction (see agent.py log_usage).
    return len(rows)


def get_events(
    db: DbSession,
    session_id: str,
    *,
    event_type: str | None = None,
) -> list[SessionEvent]:
    """Get all events for a session, ordered by seq."""
    q = db.query(SessionEvent).filter(SessionEvent.session_id == session_id)
    if event_type is not None:
        q = q.filter(SessionEvent.event_type == event_type)
    return q.order_by(SessionEvent.seq).all()
