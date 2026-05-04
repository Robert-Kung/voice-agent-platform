"""Session query endpoints."""

import json
import logging
import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import SessionDetail, SessionEventOut, SessionSummary
from db import session_store
from db.models import Session as SessionModel
from db.models import SessionEvent

logger = logging.getLogger("api.sessions")

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
    logger.info(
        "list sessions: profile_id=%s status=%s limit=%d offset=%d → %d rows",
        profile_id,
        status,
        limit,
        offset,
        len(sessions),
    )
    return [_summary_to_out(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionDetail)
def get_session_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
):
    sess = session_store.get_session(db, session_id)
    if sess is None:
        logger.warning("get session 404: id=%s", session_id)
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
        logger.warning("get session events 404: id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session not found")
    events = session_store.get_events(db, session_id, event_type=event_type)
    logger.info(
        "session events: id=%s event_type=%s → %d events", session_id, event_type, len(events)
    )
    return [_event_to_out(e) for e in events]


@router.get("/{session_id}/livekit-link")
def get_livekit_link_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
):
    """Return a LiveKit Cloud Agents dashboard URL the operator can open to find
    this session by room name. With LIVEKIT_CLOUD_PROJECT set, the URL deep-links
    into that project's Agents page; otherwise it points at the global Agents
    page and the response includes a note nudging the caller to set the env var."""
    sess = session_store.get_session(db, session_id)
    if sess is None:
        logger.warning("livekit-link 404: id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    project = os.environ.get("LIVEKIT_CLOUD_PROJECT", "")
    room_encoded = quote(sess.room_name, safe="")
    if project:
        project_encoded = quote(project, safe="")
        url = f"https://cloud.livekit.io/projects/{project_encoded}/agents"
        note = (
            "Opened the project Agents dashboard. "
            "Use the room name to find the session in Logs/Insights."
        )
    else:
        url = "https://cloud.livekit.io/agents"
        note = (
            "Set LIVEKIT_CLOUD_PROJECT for a direct project dashboard link. "
            "Then search by room name."
        )

    logger.info(
        "livekit-link: id=%s room=%s project_env=%s",
        session_id,
        sess.room_name,
        bool(project),
    )
    return {
        "session_id": session_id,
        "room_name": sess.room_name,
        "url": url,
        "note": note,
        "room_query": room_encoded,
    }
