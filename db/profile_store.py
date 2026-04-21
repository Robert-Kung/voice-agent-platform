"""Profile CRUD operations."""

import json
import os
import pathlib
import tempfile
from datetime import datetime, timezone

import yaml
from sqlalchemy.orm import Session

from db.models import Profile

# Directory holding on-disk YAML profiles (baked into the Cloud image at build time).
PROFILES_DIR = pathlib.Path(__file__).parent.parent / "profiles"


# Whitelist of Profile columns that, when updated, require a YAML re-export
# before the change can reach the Cloud image. Edits to columns NOT in this
# set (e.g. display_name) are safe to leave is_dirty unchanged.
_YAML_RELEVANT_FIELDS = {"config_json"}


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
        is_dirty=True,  # new profile → YAML doesn't exist on Cloud image yet
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

    _UPDATABLE_FIELDS = {"display_name", "description", "config_json", "is_active"}
    yaml_changed = False
    for key, value in kwargs.items():
        if key in _UPDATABLE_FIELDS:
            if key in _YAML_RELEVANT_FIELDS and getattr(profile, key) != value:
                yaml_changed = True
            setattr(profile, key, value)

    if yaml_changed:
        profile.is_dirty = True

    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return profile


def deactivate_profile(db: Session, profile_id: str) -> Profile | None:
    """Soft-delete a profile by setting is_active=False."""
    return update_profile(db, profile_id, is_active=False)


def mark_profile_deployed(db: Session, profile_id: str) -> Profile | None:
    """Clear is_dirty and stamp last_deployed_at. Call after successful export+deploy."""
    profile = db.get(Profile, profile_id)
    if profile is None:
        return None
    profile.is_dirty = False
    profile.last_deployed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return profile


def set_live_profile(db: Session, profile_id: str) -> Profile | None:
    """Mark this profile as the live one on Cloud (AGENT_PROFILE target).

    Atomically clears is_live on every other profile. Call after a successful
    `lk agent update-secrets AGENT_PROFILE=<name>` OR after a single-profile
    deploy (which flips AGENT_PROFILE as part of the same operation).
    """
    profile = db.get(Profile, profile_id)
    if profile is None:
        return None
    db.query(Profile).filter(Profile.id != profile_id).update({Profile.is_live: False})
    profile.is_live = True
    db.commit()
    db.refresh(profile)
    return profile


def mark_all_profiles_clean(db: Session) -> int:
    """Clear is_dirty for all active profiles after a full deploy. Returns count."""
    now = datetime.now(timezone.utc)
    profiles = db.query(Profile).filter(Profile.is_active.is_(True)).all()
    for p in profiles:
        p.is_dirty = False
        p.last_deployed_at = now
    db.commit()
    return len(profiles)


# ── DB → YAML export ──────────────────────────────────────────


def _atomic_write(path: pathlib.Path, text: str) -> None:
    """Write text to path via a temp file + rename, so readers never see a half-written file.

    Falls back to writing via /tmp when the target directory is not writable
    (e.g. a bind-mounted volume owned by a different UID inside Docker).
    """
    import shutil as _shutil

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    except PermissionError:
        # Target dir not writable — use system temp dir and fall back to
        # cross-device shutil.move (copy + unlink).
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            os.replace(tmp, path)
        except OSError:
            # os.replace fails across filesystems; use shutil.move instead.
            _shutil.move(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def export_profile_yaml(profile: Profile, profiles_dir: pathlib.Path = PROFILES_DIR) -> pathlib.Path:
    """Write the profile's config_json back to <profiles_dir>/<name>.yaml.

    Returns the destination path. Does NOT clear is_dirty — call
    `mark_profile_deployed` after a successful `lk agent deploy`.
    """
    data = json.loads(profile.config_json) if profile.config_json else {}
    dest = profiles_dir / f"{profile.name}.yaml"
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    _atomic_write(dest, text)
    return dest


def export_all_active_profiles(db: Session, profiles_dir: pathlib.Path = PROFILES_DIR) -> list[str]:
    """Export every active profile to <profiles_dir>/<name>.yaml. Returns written names."""
    written: list[str] = []
    for p in db.query(Profile).filter(Profile.is_active.is_(True)).all():
        export_profile_yaml(p, profiles_dir)
        written.append(p.name)
    return written
