"""Profile-scoped text test run endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_admin
from api.schemas import (
    ProfileTestRunDetail,
    ProfileTestRunEventOut,
    ProfileTestRunSummary,
    ProfileTextTestRequest,
)
from db import profile_store, test_run_store
from db.models import ProfileTestRun, ProfileTestRunEvent
from runtime.profile_test_runner import TextTestRequest, run_profile_text_test

logger = logging.getLogger("api.profile_test_runs")

router = APIRouter(
    prefix="/api/profiles/{profile_id}/test-runs",
    tags=["profile-test-runs"],
    dependencies=[Depends(require_admin)],
)


def _run_to_summary(run: ProfileTestRun) -> ProfileTestRunSummary:
    return ProfileTestRunSummary(
        id=run.id,
        profile_id=run.profile_id,
        status=run.status,
        tool_execution_mode=run.tool_execution_mode,
        user_message=run.user_message,
        profile_config_hash=run.profile_config_hash,
        profile_snapshot_at=run.profile_snapshot_at,
        final_summary=test_run_store.parse_summary(run),
        created_at=run.created_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
    )


def _event_to_out(event: ProfileTestRunEvent) -> ProfileTestRunEventOut:
    return ProfileTestRunEventOut(
        id=event.id,
        seq=event.seq,
        event_type=event.event_type,
        severity=event.severity,
        timestamp=event.timestamp,
        payload=test_run_store.parse_event_payload(event),
    )


def _run_to_detail(run: ProfileTestRun, events: list[ProfileTestRunEvent]) -> ProfileTestRunDetail:
    return ProfileTestRunDetail(**_run_to_summary(run).model_dump(), events=[_event_to_out(e) for e in events])


@router.post(
    "",
    response_model=ProfileTestRunDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_profile_test_run_endpoint(
    profile_id: str,
    payload: ProfileTextTestRequest,
    db: Session = Depends(get_db),
):
    profile = profile_store.get_profile(db, profile_id)
    if profile is None:
        logger.warning("create profile test run 404: profile_id=%s", profile_id)
        raise HTTPException(status_code=404, detail="Profile not found")

    run = run_profile_text_test(
        db,
        profile=profile,
        request=TextTestRequest(
            message=payload.message,
            tool_execution_mode=payload.tool_execution_mode,
        ),
    )
    events = test_run_store.get_events(db, run.id)
    logger.info(
        "create profile test run: profile_id=%s run_id=%s status=%s events=%d",
        profile_id,
        run.id,
        run.status,
        len(events),
    )
    return _run_to_detail(run, events)


@router.get("", response_model=list[ProfileTestRunSummary])
def list_profile_test_runs_endpoint(
    profile_id: str,
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    profile = profile_store.get_profile(db, profile_id)
    if profile is None:
        logger.warning("list profile test runs 404: profile_id=%s", profile_id)
        raise HTTPException(status_code=404, detail="Profile not found")

    runs = test_run_store.list_runs(db, profile_id=profile_id, limit=limit, offset=offset)
    total = test_run_store.count_runs(db, profile_id=profile_id)
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    logger.info(
        "list profile test runs: profile_id=%s limit=%d offset=%d -> %d/%d rows",
        profile_id,
        limit,
        offset,
        len(runs),
        total,
    )
    return [_run_to_summary(run) for run in runs]


@router.get("/{run_id}", response_model=ProfileTestRunDetail)
def get_profile_test_run_endpoint(
    profile_id: str,
    run_id: str,
    db: Session = Depends(get_db),
):
    run = test_run_store.get_run_for_profile(db, profile_id=profile_id, run_id=run_id)
    if run is None:
        logger.warning("get profile test run 404: profile_id=%s run_id=%s", profile_id, run_id)
        raise HTTPException(status_code=404, detail="Test run not found")
    events = test_run_store.get_events(db, run.id)
    return _run_to_detail(run, events)
