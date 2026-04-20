"""Profile CRUD endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import get_db, require_admin
from api.schemas import ProfileCreate, ProfileOut, ProfileUpdate
from db import profile_store
from db.models import Profile

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


def _to_out(profile: Profile) -> ProfileOut:
    """Convert DB model to API schema (parses config_json)."""
    return ProfileOut(
        id=profile.id,
        name=profile.name,
        display_name=profile.display_name,
        description=profile.description,
        is_active=profile.is_active,
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
    return [_to_out(p) for p in profiles]


@router.post("", response_model=ProfileOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_profile_endpoint(
    payload: ProfileCreate,
    db: Session = Depends(get_db),
):
    existing = profile_store.get_profile_by_name(db, payload.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Profile '{payload.name}' already exists",
        )

    profile = profile_store.create_profile(
        db,
        name=payload.name,
        display_name=payload.display_name or payload.name,
        description=payload.description,
        config_json=payload.config,
        is_active=payload.is_active,
    )
    return _to_out(profile)


@router.get("/{profile_id}", response_model=ProfileOut)
def get_profile_endpoint(
    profile_id: str,
    db: Session = Depends(get_db),
):
    profile = profile_store.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _to_out(profile)


@router.patch("/{profile_id}", response_model=ProfileOut, dependencies=[Depends(require_admin)])
def update_profile_endpoint(
    profile_id: str,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
):
    update_data = payload.model_dump(exclude_unset=True)
    if "config" in update_data:
        update_data["config_json"] = update_data.pop("config")

    profile = profile_store.update_profile(db, profile_id, **update_data)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _to_out(profile)


@router.delete("/{profile_id}", response_model=ProfileOut, dependencies=[Depends(require_admin)])
def deactivate_profile_endpoint(
    profile_id: str,
    db: Session = Depends(get_db),
):
    profile = profile_store.deactivate_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _to_out(profile)
