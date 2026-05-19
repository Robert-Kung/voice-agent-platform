"""Aggregate statistics endpoints."""

import logging
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import DailyStatsOut, ProfileStatsOut
from db.models import Profile
from db.models import Session as SessionModel

logger = logging.getLogger("api.stats")

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/profiles", response_model=list[ProfileStatsOut])
def profile_stats_endpoint(
    db: Session = Depends(get_db),
):
    """Aggregate session stats grouped by profile."""
    rows = (
        db.query(
            SessionModel.profile_id,
            Profile.name,
            func.count(SessionModel.id).label("cnt"),
            func.coalesce(func.sum(SessionModel.duration_seconds), 0.0).label("total_dur"),
            func.coalesce(func.sum(SessionModel.total_cost_usd), 0.0).label("total_cost"),
        )
        .outerjoin(Profile, SessionModel.profile_id == Profile.id)
        .group_by(SessionModel.profile_id, Profile.name)
        .all()
    )

    results = []
    for row in rows:
        cnt = row.cnt or 0
        total_dur = float(row.total_dur or 0.0)
        results.append(
            ProfileStatsOut(
                profile_id=row.profile_id,
                profile_name=row.name,
                session_count=cnt,
                total_duration_seconds=total_dur,
                total_cost_usd=float(row.total_cost or 0.0),
                avg_duration_seconds=total_dur / cnt if cnt else 0.0,
            )
        )
    logger.info("stats/profiles: %d profile buckets", len(results))
    return results


@router.get("/daily", response_model=list[DailyStatsOut])
def daily_stats_endpoint(
    profile_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Daily aggregate stats (grouped by started_at date)."""
    q = db.query(SessionModel)
    if profile_id:
        q = q.filter(SessionModel.profile_id == profile_id)

    # Group in Python to keep DB-portable (SQLite date functions differ)
    buckets: dict[str, dict] = defaultdict(lambda: {"count": 0, "duration": 0.0, "cost": 0.0})
    for sess in q.all():
        if sess.started_at is None:
            continue
        started = sess.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        day = started.date().isoformat()
        buckets[day]["count"] += 1
        buckets[day]["duration"] += sess.duration_seconds or 0.0
        buckets[day]["cost"] += sess.total_cost_usd or 0.0

    logger.info(
        "stats/daily: profile_id=%s → %d day buckets", profile_id, len(buckets)
    )
    return [
        DailyStatsOut(
            date=day,
            session_count=data["count"],
            total_duration_seconds=data["duration"],
            total_cost_usd=data["cost"],
        )
        for day, data in sorted(buckets.items())
    ]
