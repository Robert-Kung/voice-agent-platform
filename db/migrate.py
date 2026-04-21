"""Database migration — create tables and import YAML profiles."""

import json
import logging
import pathlib

import yaml
from sqlalchemy.orm import Session

from db.engine import get_engine, get_session_factory, init_db
from db.models import Profile

logger = logging.getLogger("db.migrate")

PROFILES_DIR = pathlib.Path(__file__).parent.parent / "profiles"


def _yaml_to_profile(yaml_path: pathlib.Path) -> dict:
    """Read a YAML profile and return kwargs for Profile model."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    name = yaml_path.stem  # e.g. "car_inspection"
    display_name = data.get("name", name)  # e.g. "車容坊加油站"

    return {
        "name": name,
        "display_name": display_name,
        "description": data.get("instructions", "")[:500],
        "config_json": json.dumps(data, ensure_ascii=False),
        "is_active": True,
        # Imported YAMLs already match the on-disk file that would be baked into
        # the next Cloud image, so start them clean.
        "is_dirty": False,
    }


def import_yaml_profiles(db_session: Session) -> int:
    """Import all YAML profiles into DB if profiles table is empty.

    Returns the number of profiles imported.
    """
    existing_count = db_session.query(Profile).count()
    if existing_count > 0:
        logger.info("Profiles table has %d rows, skipping YAML import.", existing_count)
        return 0

    yaml_files = sorted(PROFILES_DIR.glob("*.yaml"))
    if not yaml_files:
        logger.warning("No YAML profiles found in %s", PROFILES_DIR)
        return 0

    imported = 0
    for yaml_path in yaml_files:
        if yaml_path.stem == "example":
            continue  # skip example profile
        try:
            kwargs = _yaml_to_profile(yaml_path)
            db_session.add(Profile(**kwargs))
            imported += 1
            logger.info("Imported profile: %s (%s)", kwargs["name"], kwargs["display_name"])
        except Exception:
            logger.exception("Failed to import %s", yaml_path)

    db_session.commit()
    logger.info("Imported %d profiles from YAML.", imported)
    return imported


def run_migration() -> None:
    """Full migration: create tables + import YAML profiles."""
    engine = get_engine()
    init_db(engine)
    logger.info("Database tables created/verified.")

    session_factory = get_session_factory(engine)
    with session_factory() as db_session:
        import_yaml_profiles(db_session)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
