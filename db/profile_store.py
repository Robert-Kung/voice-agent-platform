"""Profile CRUD operations."""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db.models import Profile


def list_profiles(db: Session, *, active_only: bool = True) -> list[Profile]:
    """List all profiles, optionally filtered by active status."""
    q = db.query(Profile)
    if active_only:
        q = q.filter(Profile.is_active == True)  # noqa: E712
    return q.order_by(Profile.name).all()


def get_profile(db: Session, profile_id: str) -> Profile | None:
    """Get a single profile by ID."""
    return db.get(Profile, profile_id)


def get_profile_by_name(db: Session, name: str) -> Profile | None:
    """Get a single profile by unique name."""
    return db.query(Profile).filter(Profile.name == name).first()


def create_profile(
    db: Session,
    *,
    name: str,
    display_name: str,
    description: str = "",
    config_json: str | dict = "{}",
    is_active: bool = True,
) -> Profile:
    """Create a new profile."""
    if isinstance(config_json, dict):
        config_json = json.dumps(config_json, ensure_ascii=False)

    profile = Profile(
        name=name,
        display_name=display_name,
        description=description,
        config_json=config_json,
        is_active=is_active,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_profile(
    db: Session,
    profile_id: str,
    **kwargs,
) -> Profile | None:
    """Update a profile. Pass only the fields to update."""
    profile = db.get(Profile, profile_id)
    if profile is None:
        return None

    if "config_json" in kwargs and isinstance(kwargs["config_json"], dict):
        kwargs["config_json"] = json.dumps(kwargs["config_json"], ensure_ascii=False)

    for key, value in kwargs.items():
        if hasattr(profile, key):
            setattr(profile, key, value)

    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return profile


def deactivate_profile(db: Session, profile_id: str) -> Profile | None:
    """Soft-delete a profile by setting is_active=False."""
    return update_profile(db, profile_id, is_active=False)
