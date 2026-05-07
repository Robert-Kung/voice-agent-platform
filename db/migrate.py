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
    """Import any YAML profiles missing from DB.

    Existing rows are NOT overwritten (DB is source of truth once an admin
    has edited a profile). Only new YAML files (not yet in DB by name) get
    imported. This way dropping a new YAML into profiles/ + restarting the
    API auto-syncs it without disturbing edited rows.

    Returns the number of profiles imported.
    """
    yaml_files = sorted(PROFILES_DIR.glob("*.yaml"))
    if not yaml_files:
        logger.warning("No YAML profiles found in %s", PROFILES_DIR)
        return 0

    existing_names = {p.name for p in db_session.query(Profile).all()}

    imported = 0
    for yaml_path in yaml_files:
        if yaml_path.stem == "example":
            continue  # skip example profile
        if yaml_path.stem in existing_names:
            continue  # DB already has it — never overwrite
        try:
            kwargs = _yaml_to_profile(yaml_path)
            db_session.add(Profile(**kwargs))
            imported += 1
            logger.info("Imported new YAML profile: %s (%s)", kwargs["name"], kwargs["display_name"])
        except Exception:
            logger.exception("Failed to import %s", yaml_path)

    if imported:
        db_session.commit()
    return imported


# Stage 1 (2026-05-04) renamed get_current_datetime → get_current_time. Old
# profile rows referencing the old name should be migrated, not dropped.
RENAMED_TOOLS = {
    "get_current_datetime": "get_current_time",
}
# Stage 1 deleted these mock-data tools entirely.
DELETED_TOOL_NAMES = {
    "check_business_status",  # replaced by services rendered into instructions
    "check_weather",
    "book_appointment",
    "search_menu",
    "calculate_price",
    "replay_last_prompt",
}
# Now auto-mounted by qa_mode / human_operator config — should not be listed
# as user-selected built-in tools.
AUTO_MOUNTED_TOOLS = {"lookup_qa", "transfer_to_human"}


def clean_legacy_tools(db_session: Session) -> int:
    """Migrate existing profile rows so config.tools matches the current
    registry: rename old names, drop deleted ones, drop auto-mounted ones.
    Tier 3 HTTP tools (entries with `endpoint`) are preserved untouched.

    Returns the number of profile rows mutated.
    """
    profiles = db_session.query(Profile).all()
    mutated = 0
    for p in profiles:
        try:
            cfg = json.loads(p.config_json) if p.config_json else {}
        except json.JSONDecodeError:
            logger.warning("Skipping %s: invalid config_json", p.name)
            continue
        tools = cfg.get("tools") or []
        if not isinstance(tools, list):
            continue
        cleaned: list = []
        seen_names: set[str] = set()
        changes: list[str] = []
        for t in tools:
            if not isinstance(t, dict):
                cleaned.append(t)
                continue
            if t.get("endpoint"):
                cleaned.append(t)  # Tier 3, keep
                continue
            name = t.get("name")
            if name in RENAMED_TOOLS:
                new_name = RENAMED_TOOLS[name]
                changes.append(f"{name}→{new_name}")
                if new_name in seen_names:
                    continue  # avoid duplicate after rename
                cleaned.append({**t, "name": new_name})
                seen_names.add(new_name)
                continue
            if name in DELETED_TOOL_NAMES or name in AUTO_MOUNTED_TOOLS:
                changes.append(f"-{name}")
                continue
            if name in seen_names:
                continue  # dedupe
            cleaned.append(t)
            if isinstance(name, str):
                seen_names.add(name)
        if not changes:
            continue
        cfg["tools"] = cleaned
        p.config_json = json.dumps(cfg, ensure_ascii=False)
        mutated += 1
        logger.info("Cleaned %s: %s", p.name, ", ".join(changes))
    if mutated:
        db_session.commit()
    return mutated


def run_migration() -> None:
    """Full migration: create tables + import YAML profiles."""
    engine = get_engine()
    init_db(engine)
    logger.info("Database tables created/verified.")

    session_factory = get_session_factory(engine)
    with session_factory() as db_session:
        import_yaml_profiles(db_session)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "clean-legacy-tools":
        engine = get_engine()
        with get_session_factory(engine)() as db:
            n = clean_legacy_tools(db)
            logger.info("clean-legacy-tools: %d profile(s) updated", n)
    else:
        run_migration()
