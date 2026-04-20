"""Session query endpoints."""

import json
import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import SessionDetail, SessionEventOut, SessionSummary
from db import session_store
from db.models import Session as SessionModel
from db.models import SessionEvent

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _summary_to_out(sess: SessionModel) -> SessionSummary:
    return SessionSummary.model_validate(sess)


def _detail_to_out(sess: SessionModel) -> SessionDetail:
    base = SessionSummary.model_validate(sess)
    raw_report = json.loads(sess.raw_report_json) if sess.raw_report_json else {}
    return SessionDetail(**base.model_dump(), raw_report=raw_report)


def _event_to_out(ev: SessionEvent) -> SessionEventOut:
    return SessionEventOut(
        id=ev.id,
        seq=ev.seq,
        event_type=ev.event_type,
        timestamp=ev.timestamp,
        payload=json.loads(ev.payload_json) if ev.payload_json else {},
    )


@router.get("", response_model=list[SessionSummary])
def list_sessions_endpoint(
    profile_id: str | None = Query(None),
    status: str | None = Query(None, pattern="^(running|completed|failed)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    sessions = session_store.list_sessions(
        db,
        profile_id=profile_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [_summary_to_out(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionDetail)
def get_session_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
):
    sess = session_store.get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _detail_to_out(sess)


@router.get("/{session_id}/events", response_model=list[SessionEventOut])
def get_session_events_endpoint(
    session_id: str,
    event_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    sess = session_store.get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    events = session_store.get_events(db, session_id, event_type=event_type)
    return [_event_to_out(e) for e in events]


@router.get("/{session_id}/livekit-link")
def get_livekit_link_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
):
    """Generate a LiveKit Cloud dashboard URL for this session's room recording."""
    sess = session_store.get_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # LiveKit Cloud URL pattern:
    # https://cloud.livekit.io/projects/{project}/sessions?room={room_name}
    project = os.environ.get("LIVEKIT_CLOUD_PROJECT", "")
    room_encoded = quote(sess.room_name, safe="")
    if project:
        url = f"https://cloud.livekit.io/projects/{quote(project, safe='')}/sessions?room={room_encoded}"
    else:
        url = f"https://cloud.livekit.io/sessions?room={room_encoded}"

    return {
        "session_id": session_id,
        "room_name": sess.room_name,
        "url": url,
        "note": "Set LIVEKIT_CLOUD_PROJECT env var for a direct project link.",
    }
