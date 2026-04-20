"""Unit tests for DB layer — profile_store, session_store, migrate."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Profile
from db import profile_store, session_store
from db.migrate import import_yaml_profiles


@pytest.fixture()
def db():
    """Create an in-memory SQLite DB and yield a session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        yield session


# ── Profile Store ────────────────────────────────────────────


class TestProfileStore:
    def test_create_and_get(self, db):
        p = profile_store.create_profile(
            db,
            name="test_profile",
            display_name="Test Profile",
            description="A test",
            config_json={"instructions": "hello"},
        )
        assert p.id is not None
        assert p.name == "test_profile"
        assert p.display_name == "Test Profile"
        assert json.loads(p.config_json) == {"instructions": "hello"}

        fetched = profile_store.get_profile(db, p.id)
        assert fetched is not None
        assert fetched.name == "test_profile"

    def test_get_by_name(self, db):
        profile_store.create_profile(db, name="alpha", display_name="Alpha")
        found = profile_store.get_profile_by_name(db, "alpha")
        assert found is not None
        assert found.display_name == "Alpha"

        assert profile_store.get_profile_by_name(db, "nonexistent") is None

    def test_list_profiles(self, db):
        profile_store.create_profile(db, name="b_profile", display_name="B")
        profile_store.create_profile(db, name="a_profile", display_name="A")
        profiles = profile_store.list_profiles(db)
        assert len(profiles) == 2
        assert profiles[0].name == "a_profile"  # sorted by name

    def test_list_active_only(self, db):
        p = profile_store.create_profile(db, name="active", display_name="Active")
        profile_store.create_profile(db, name="inactive", display_name="Inactive", is_active=False)

        active = profile_store.list_profiles(db, active_only=True)
        assert len(active) == 1
        assert active[0].id == p.id

        all_profiles = profile_store.list_profiles(db, active_only=False)
        assert len(all_profiles) == 2

    def test_update_profile(self, db):
        p = profile_store.create_profile(db, name="orig", display_name="Original")
        updated = profile_store.update_profile(db, p.id, display_name="Updated")
        assert updated is not None
        assert updated.display_name == "Updated"

    def test_update_nonexistent(self, db):
        result = profile_store.update_profile(db, "fake-id", display_name="X")
        assert result is None

    def test_deactivate(self, db):
        p = profile_store.create_profile(db, name="to_deactivate", display_name="D")
        assert p.is_active is True

        deactivated = profile_store.deactivate_profile(db, p.id)
        assert deactivated is not None
        assert deactivated.is_active is False


# ── Session Store ────────────────────────────────────────────


class TestSessionStore:
    def _make_profile(self, db):
        return profile_store.create_profile(db, name="sess_profile", display_name="SP")

    def test_create_session(self, db):
        p = self._make_profile(db)
        s = session_store.create_session(db, room_name="room-1", profile_id=p.id)
        assert s.status == "running"
        assert s.room_name == "room-1"
        assert s.profile_id == p.id

    def test_complete_session(self, db):
        s = session_store.create_session(db, room_name="room-2")
        completed = session_store.complete_session(
            db,
            s.id,
            shutdown_reason="user_left",
            duration_seconds=120.5,
            total_cost_usd=0.03,
            raw_report_json={"summary": "ok"},
        )
        assert completed is not None
        assert completed.status == "completed"
        assert completed.ended_at is not None
        assert completed.duration_seconds == 120.5
        assert completed.total_cost_usd == 0.03

    def test_fail_session(self, db):
        s = session_store.create_session(db, room_name="room-3")
        failed = session_store.fail_session(db, s.id, reason="crash")
        assert failed is not None
        assert failed.status == "failed"
        assert failed.shutdown_reason == "crash"

    def test_list_sessions(self, db):
        p = self._make_profile(db)
        session_store.create_session(db, room_name="r1", profile_id=p.id)
        session_store.create_session(db, room_name="r2", profile_id=p.id)
        session_store.create_session(db, room_name="r3")

        all_sessions = session_store.list_sessions(db)
        assert len(all_sessions) == 3

        filtered = session_store.list_sessions(db, profile_id=p.id)
        assert len(filtered) == 2

    def test_list_sessions_by_status(self, db):
        s1 = session_store.create_session(db, room_name="r1")
        session_store.create_session(db, room_name="r2")
        session_store.complete_session(db, s1.id)

        running = session_store.list_sessions(db, status="running")
        assert len(running) == 1

        completed = session_store.list_sessions(db, status="completed")
        assert len(completed) == 1

    def test_mark_stale_sessions_reconciles_old_running(self, db):
        """Running sessions older than cutoff → status=failed."""
        from datetime import datetime, timedelta, timezone

        # Stale: started 2 hours ago, still "running"
        stale = session_store.create_session(db, room_name="stale-room")
        stale.started_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        db.commit()

        # Fresh: just started, still "running"
        fresh = session_store.create_session(db, room_name="fresh-room")

        # Completed: should not be touched
        done = session_store.create_session(db, room_name="done-room")
        session_store.complete_session(db, done.id, shutdown_reason="normal")

        reconciled = session_store.mark_stale_sessions(db, max_age_hours=1.0)
        assert reconciled == 1

        db.refresh(stale)
        db.refresh(fresh)
        db.refresh(done)
        assert stale.status == "failed"
        assert "stale" in stale.shutdown_reason
        assert fresh.status == "running"
        assert done.status == "completed"

    def test_mark_stale_sessions_no_op_when_none(self, db):
        session_store.create_session(db, room_name="fresh")
        assert session_store.mark_stale_sessions(db, max_age_hours=1.0) == 0

    def test_add_and_get_events(self, db):
        s = session_store.create_session(db, room_name="room-ev")
        events = [
            {"seq": 1, "event_type": "user_message", "payload_json": {"text": "hi"}},
            {"seq": 2, "event_type": "agent_message", "payload_json": {"text": "hello"}},
            {"seq": 3, "event_type": "tool_call", "payload_json": {"tool": "search"}},
        ]
        count = session_store.add_events(db, s.id, events)
        db.commit()  # add_events no longer commits (atomic write support)
        assert count == 3

        all_events = session_store.get_events(db, s.id)
        assert len(all_events) == 3
        assert all_events[0].event_type == "user_message"
        assert json.loads(all_events[0].payload_json) == {"text": "hi"}

        tool_events = session_store.get_events(db, s.id, event_type="tool_call")
        assert len(tool_events) == 1


# ── YAML Import ──────────────────────────────────────────────


class TestYamlImport:
    def test_import_populates_empty_db(self, db):
        count = import_yaml_profiles(db)
        assert count > 0

        profiles = profile_store.list_profiles(db, active_only=False)
        assert len(profiles) == count

        # Should have car_inspection and restaurant at minimum
        names = {p.name for p in profiles}
        assert "car_inspection" in names
        assert "restaurant" in names

        # config_json should be valid JSON
        for p in profiles:
            data = json.loads(p.config_json)
            assert isinstance(data, dict)
            assert "instructions" in data

    def test_import_skips_nonempty_db(self, db):
        profile_store.create_profile(db, name="existing", display_name="Existing")
        count = import_yaml_profiles(db)
        assert count == 0
