"""Profile CRUD endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from agent_tools import get_available_tools
from api.deps import get_db, require_admin
from api.schemas import ProfileCreate, ProfileOut, ProfileUpdate
from db import profile_store
from db.models import Profile
from runtime.graph import validate_profile_config

logger = logging.getLogger("api.profiles")

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def _assert_graph_saveable(config: dict | None) -> None:
    """Backend hard validation for graph-mode saves (graph-runtime-validation spec).

    The frontend `validateGraph` is UX-only and bypassable by direct API writes,
    so structural errors AND the graph+realtime mode conflict are enforced here.
    Passthrough (None result) for prompt-mode profiles or those with no graph block.
    """
    if not config:
        return
    declared_mode = (config.get("models") or {}).get("mode")
    result = validate_profile_config(config, get_available_tools(), mode=declared_mode)
    if result is None or result.valid:
        return
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "message": "graph 結構驗證未通過，無法存檔",
            "errors": [{"code": e.code, "message": e.message} for e in result.errors],
            "warnings": [{"code": w.code, "message": w.message} for w in result.warnings],
        },
    )


def _to_out(profile: Profile) -> ProfileOut:
    """Convert DB model to API schema (parses config_json)."""
    return ProfileOut(
        id=profile.id,
        name=profile.name,
        display_name=profile.display_name,
        description=profile.description,
        is_active=profile.is_active,
        is_dirty=profile.is_dirty,
        is_live=profile.is_live,
        last_deployed_at=profile.last_deployed_at,
        config=json.loads(profile.config_json) if profile.config_json else {},
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("", response_model=list[ProfileOut])
def list_profiles_endpoint(
    active_only: bool = Query(True, description="Only return active profiles"),
    db: Session = Depends(get_db),
):
    profiles = profile_store.list_profiles(db, active_only=active_only)
    logger.info("list profiles: active_only=%s → %d rows", active_only, len(profiles))
    return [_to_out(p) for p in profiles]


@router.post("", response_model=ProfileOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_profile_endpoint(
    payload: ProfileCreate,
    db: Session = Depends(get_db),
):
    existing = profile_store.get_profile_by_name(db, payload.name)
    if existing is not None:
        logger.warning("create profile rejected: name=%s already exists (id=%s)", payload.name, existing.id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Profile '{payload.name}' already exists",
        )

    _assert_graph_saveable(payload.config)

    profile = profile_store.create_profile(
        db,
        name=payload.name,
        display_name=payload.display_name or payload.name,
        description=payload.description,
        config_json=payload.config,
        is_active=payload.is_active,
    )
    logger.info(
        "create profile: id=%s name=%s is_active=%s config_keys=%s",
        profile.id,
        profile.name,
        profile.is_active,
        sorted((payload.config or {}).keys()),
    )
    return _to_out(profile)


@router.get("/{profile_id}", response_model=ProfileOut)
def get_profile_endpoint(
    profile_id: str,
    db: Session = Depends(get_db),
):
    profile = profile_store.get_profile(db, profile_id)
    if profile is None:
        logger.warning("get profile 404: id=%s", profile_id)
        raise HTTPException(status_code=404, detail="Profile not found")
    return _to_out(profile)


@router.patch("/{profile_id}", response_model=ProfileOut, dependencies=[Depends(require_admin)])
def update_profile_endpoint(
    profile_id: str,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
):
    update_data = payload.model_dump(exclude_unset=True)
    changed_fields = sorted(update_data.keys())
    if "config" in update_data:
        _assert_graph_saveable(update_data["config"])
        update_data["config_json"] = update_data.pop("config")

    profile = profile_store.update_profile(db, profile_id, **update_data)
    if profile is None:
        logger.warning("update profile 404: id=%s fields=%s", profile_id, changed_fields)
        raise HTTPException(status_code=404, detail="Profile not found")
    logger.info(
        "update profile: id=%s name=%s fields=%s is_dirty=%s",
        profile.id,
        profile.name,
        changed_fields,
        profile.is_dirty,
    )
    return _to_out(profile)


@router.delete("/{profile_id}", response_model=ProfileOut, dependencies=[Depends(require_admin)])
def deactivate_profile_endpoint(
    profile_id: str,
    db: Session = Depends(get_db),
):
    profile = profile_store.deactivate_profile(db, profile_id)
    if profile is None:
        logger.warning("deactivate profile 404: id=%s", profile_id)
        raise HTTPException(status_code=404, detail="Profile not found")
    logger.info("deactivate profile: id=%s name=%s", profile.id, profile.name)
    return _to_out(profile)
