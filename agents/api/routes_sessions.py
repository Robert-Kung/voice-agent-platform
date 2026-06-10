"""Session query endpoints."""

import json
import logging
import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import SessionDetail, SessionEventOut, SessionSummary
from db import session_store
from db.cost import compute_cost
from db.models import Session as SessionModel
from db.models import SessionEvent

logger = logging.getLogger("api.sessions")

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _derive_agent_mode(sess: SessionModel, raw_report: dict | None = None) -> str | None:
    """Infer agent_mode for legacy rows that pre-date the column.

    New rows have it set on insert. Old rows fall back to a heuristic:
    audio token presence in the usage_summary indicates a realtime model.
    """
    if sess.agent_mode:
        return sess.agent_mode
    report = raw_report
    if report is None:
        report = json.loads(sess.raw_report_json) if sess.raw_report_json else {}
    usage = report.get("usage_summary", {}) if isinstance(report, dict) else {}
    if not isinstance(usage, dict):
        return None
    if usage.get("llm_input_audio_tokens") or usage.get("llm_output_audio_tokens"):
        return "realtime"
    if usage.get("llm_prompt_tokens") or usage.get("llm_completion_tokens"):
        return "pipeline"
    return None


def _selected_models(sess: SessionModel) -> dict | None:
    """Parse the resolver-selected model names recorded on the session row."""
    if not sess.model_names_json:
        return None
    try:
        return json.loads(sess.model_names_json)
    except (json.JSONDecodeError, TypeError):
        return None


def _summary_to_out(sess: SessionModel) -> SessionSummary:
    out = SessionSummary.model_validate(sess)
    if out.agent_mode is None:
        out.agent_mode = _derive_agent_mode(sess)
    # Freeze: stored cost is authoritative — a rate-table edit must NOT re-price a
    # completed session. Only recompute when the stored total is missing (legacy
    # rows whose total was null because the old compute_cost couldn't price audio
    # tokens). When we do recompute, drive it with the row's recorded model names.
    if out.total_cost_usd is None and out.agent_mode:
        report = json.loads(sess.raw_report_json) if sess.raw_report_json else {}
        usage = report.get("usage_summary") if isinstance(report, dict) else None
        if isinstance(usage, dict):
            recomputed = compute_cost(usage, agent_mode=out.agent_mode, selected=_selected_models(sess))
            if recomputed.get("total_usd") is not None:
                out.total_cost_usd = recomputed["total_usd"]
    return out


def _detail_to_out(sess: SessionModel) -> SessionDetail:
    raw_report = json.loads(sess.raw_report_json) if sess.raw_report_json else {}
    base = SessionSummary.model_validate(sess)
    if base.agent_mode is None:
        base.agent_mode = _derive_agent_mode(sess, raw_report)
    # Freeze: keep the stored cost breakdown. Only recompute (and merge) when the
    # stored cost is missing/null — legacy rows that never got a price. Driven by
    # the row's recorded model names so the backfill is correct, not guessed.
    if isinstance(raw_report, dict):
        usage = raw_report.get("usage_summary")
        existing_cost = raw_report.get("cost") or {}
        if isinstance(usage, dict) and (
            not isinstance(existing_cost, dict) or existing_cost.get("total_usd") is None
        ):
            recomputed = compute_cost(usage, agent_mode=base.agent_mode, selected=_selected_models(sess))
            raw_report["cost"] = recomputed
            if base.total_cost_usd is None and recomputed.get("total_usd") is not None:
                base.total_cost_usd = recomputed["total_usd"]
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
    response: Response,
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
    total = session_store.count_sessions(db, profile_id=profile_id, status=status)
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    logger.info(
        "list sessions: profile_id=%s status=%s limit=%d offset=%d → %d/%d rows",
        profile_id,
        status,
        limit,
        offset,
        len(sessions),
        total,
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
