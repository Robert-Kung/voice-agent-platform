"""Smoke tests for the Management API."""

import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from api.deps import get_db
from db.models import Base


@pytest.fixture()
def client(monkeypatch):
    """Create a TestClient with an in-memory DB override (StaticPool shares connection).

    ADMIN_API_TOKEN is cleared so write endpoints run in dev-mode (no auth).
    Auth-enforcement tests use the `secured_client` fixture below instead.
    """
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.rollback()
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestProfilesAPI:
    def test_create_and_list(self, client):
        r = client.post("/api/profiles", json={
            "name": "api_test_profile",
            "display_name": "API Test",
            "description": "Test profile",
            "config": {"instructions": "hello", "tools": []},
        })
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "api_test_profile"
        assert data["config"]["instructions"] == "hello"
        profile_id = data["id"]

        r = client.get("/api/profiles")
        assert r.status_code == 200
        profiles = r.json()
        assert any(p["id"] == profile_id for p in profiles)

    def test_create_duplicate_name_409(self, client):
        client.post("/api/profiles", json={"name": "dup", "display_name": "Dup"})
        r = client.post("/api/profiles", json={"name": "dup", "display_name": "Dup2"})
        assert r.status_code == 409

    def test_get_by_id(self, client):
        r = client.post("/api/profiles", json={"name": "get_test", "display_name": "Get"})
        profile_id = r.json()["id"]

        r = client.get(f"/api/profiles/{profile_id}")
        assert r.status_code == 200
        assert r.json()["name"] == "get_test"

    def test_get_nonexistent_404(self, client):
        r = client.get("/api/profiles/fake-id")
        assert r.status_code == 404

    def test_update_profile(self, client):
        r = client.post("/api/profiles", json={"name": "upd", "display_name": "Original"})
        profile_id = r.json()["id"]

        r = client.patch(f"/api/profiles/{profile_id}", json={"display_name": "Updated"})
        assert r.status_code == 200
        assert r.json()["display_name"] == "Updated"

    def test_deactivate_profile(self, client):
        r = client.post("/api/profiles", json={"name": "del_me", "display_name": "D"})
        profile_id = r.json()["id"]

        r = client.delete(f"/api/profiles/{profile_id}")
        assert r.status_code == 200
        assert r.json()["is_active"] is False


class TestSessionsAPI:
    def test_list_empty(self, client):
        r = client.get("/api/sessions")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_nonexistent_404(self, client):
        r = client.get("/api/sessions/fake-id")
        assert r.status_code == 404

    def test_events_for_nonexistent_session_404(self, client):
        r = client.get("/api/sessions/fake-id/events")
        assert r.status_code == 404

    def test_livekit_link_with_project(self, client, monkeypatch):
        from api import routes_sessions

        monkeypatch.setenv("LIVEKIT_CLOUD_PROJECT", "proj demo")
        monkeypatch.setattr(
            routes_sessions.session_store,
            "get_session",
            lambda _db, _sid: SimpleNamespace(room_name="room / A"),
        )

        r = client.get("/api/sessions/s1/livekit-link")
        assert r.status_code == 200
        data = r.json()
        assert data["url"] == "https://cloud.livekit.io/projects/proj%20demo/agents"
        assert data["room_query"] == "room%20%2F%20A"

    def test_livekit_link_without_project(self, client, monkeypatch):
        from api import routes_sessions

        monkeypatch.delenv("LIVEKIT_CLOUD_PROJECT", raising=False)
        monkeypatch.setattr(
            routes_sessions.session_store,
            "get_session",
            lambda _db, _sid: SimpleNamespace(room_name="room_B"),
        )

        r = client.get("/api/sessions/s1/livekit-link")
        assert r.status_code == 200
        data = r.json()
        assert data["url"] == "https://cloud.livekit.io/agents"
        assert data["room_query"] == "room_B"


class TestStatsAPI:
    def test_profile_stats_empty(self, client):
        r = client.get("/api/stats/profiles")
        assert r.status_code == 200
        assert r.json() == []

    def test_daily_stats_empty(self, client):
        r = client.get("/api/stats/daily")
        assert r.status_code == 200
        assert r.json() == []


class TestAdminAuth:
    """Verify X-Admin-Token enforcement on write endpoints."""

    @pytest.fixture()
    def secured_client(self):
        """Client with ADMIN_API_TOKEN set — write endpoints require token."""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        TestingSessionLocal = sessionmaker(bind=engine)

        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.rollback()
                db.close()

        old_token = os.environ.get("ADMIN_API_TOKEN")
        os.environ["ADMIN_API_TOKEN"] = "test-secret-token"

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()
        if old_token is None:
            os.environ.pop("ADMIN_API_TOKEN", None)
        else:
            os.environ["ADMIN_API_TOKEN"] = old_token

    def test_post_without_token_rejected(self, secured_client):
        r = secured_client.post("/api/profiles", json={"name": "x", "display_name": "X"})
        assert r.status_code == 401

    def test_post_with_wrong_token_rejected(self, secured_client):
        r = secured_client.post(
            "/api/profiles",
            json={"name": "x", "display_name": "X"},
            headers={"X-Admin-Token": "wrong"},
        )
        assert r.status_code == 401

    def test_post_with_correct_token_ok(self, secured_client):
        r = secured_client.post(
            "/api/profiles",
            json={"name": "auth_test", "display_name": "Auth"},
            headers={"X-Admin-Token": "test-secret-token"},
        )
        assert r.status_code == 201

    def test_get_without_token_ok(self, secured_client):
        """GET (read) endpoints should work without a token."""
        r = secured_client.get("/api/profiles")
        assert r.status_code == 200


class TestTestRoutesGates:
    """Verify the layered safety gates on /api/test/* — these endpoints fork
    `agent.py connect`, so a regression here is a remote-process-spawning
    surface. We test the gates only, never actually spawn a subprocess.

    api/main.py mounts the router conditionally on ENABLE_TEST_ROUTES (so on
    the default app the routes don't even exist), but we test the
    *router itself* so the dependency wiring is exercised directly. To do
    that we build a fresh FastAPI instance per fixture and include only the
    test_router on it.
    """

    @pytest.fixture()
    def gated_client(self, monkeypatch):
        """Fresh app with only routes_test mounted and env vars under test
        control. monkeypatch resets env on teardown so other tests aren't
        affected."""
        from fastapi import FastAPI
        from api.routes_test import router as test_router

        # Default to "fully closed" — individual tests opt into looser config.
        monkeypatch.delenv("ENABLE_TEST_ROUTES", raising=False)
        monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)

        app_under_test = FastAPI()
        app_under_test.include_router(test_router)
        with TestClient(app_under_test) as c:
            yield c

    def test_404_when_enable_flag_unset(self, gated_client):
        # ENABLE_TEST_ROUTES not set → _require_test_routes_enabled raises 404.
        r = gated_client.post("/api/test/start", json={"profile": "x"})
        assert r.status_code == 404

    def test_503_when_token_missing_even_if_enabled(self, gated_client, monkeypatch):
        # ENABLE_TEST_ROUTES set but ADMIN_API_TOKEN unset → 503 (refuses to
        # rely on require_admin's dev-bypass for a process-spawning route).
        monkeypatch.setenv("ENABLE_TEST_ROUTES", "1")
        r = gated_client.post("/api/test/start", json={"profile": "x"})
        assert r.status_code == 503

    def test_401_when_token_wrong(self, gated_client, monkeypatch):
        monkeypatch.setenv("ENABLE_TEST_ROUTES", "1")
        monkeypatch.setenv("ADMIN_API_TOKEN", "secret")
        r = gated_client.post(
            "/api/test/start",
            json={"profile": "x"},
            headers={"X-Admin-Token": "wrong"},
        )
        assert r.status_code == 401

    def test_400_for_invalid_profile_name(self, gated_client, monkeypatch):
        # Path-traversal characters in profile must be rejected before the
        # subprocess is even considered. Auth all OK; only validation fires.
        monkeypatch.setenv("ENABLE_TEST_ROUTES", "1")
        monkeypatch.setenv("ADMIN_API_TOKEN", "secret")
        r = gated_client.post(
            "/api/test/start",
            json={"profile": "../etc/passwd"},
            headers={"X-Admin-Token": "secret"},
        )
        assert r.status_code == 400

    def test_400_for_empty_profile_name(self, gated_client, monkeypatch):
        monkeypatch.setenv("ENABLE_TEST_ROUTES", "1")
        monkeypatch.setenv("ADMIN_API_TOKEN", "secret")
        r = gated_client.post(
            "/api/test/start",
            json={"profile": ""},
            headers={"X-Admin-Token": "secret"},
        )
        assert r.status_code == 400

    def test_400_for_too_long_profile_name(self, gated_client, monkeypatch):
        monkeypatch.setenv("ENABLE_TEST_ROUTES", "1")
        monkeypatch.setenv("ADMIN_API_TOKEN", "secret")
        r = gated_client.post(
            "/api/test/start",
            json={"profile": "x" * 200},
            headers={"X-Admin-Token": "secret"},
        )
        assert r.status_code == 400

    def test_400_for_invalid_room_name_on_stop(self, gated_client, monkeypatch):
        # /stop validates room separately (path param). Auth all OK; only
        # the room-shape validator fires.
        monkeypatch.setenv("ENABLE_TEST_ROUTES", "1")
        monkeypatch.setenv("ADMIN_API_TOKEN", "secret")
        # Path-traversal-shaped room → 400, never reaches the kill logic.
        r = gated_client.delete(
            "/api/test/stop/has.dots.and.slashes",
            headers={"X-Admin-Token": "secret"},
        )
        assert r.status_code == 400

    def test_running_endpoint_passes_gates_and_returns_empty(
        self, gated_client, monkeypatch
    ):
        # Smoke check that GET /api/test/running fires through both gates
        # and returns the expected shape on a clean process table.
        monkeypatch.setenv("ENABLE_TEST_ROUTES", "1")
        monkeypatch.setenv("ADMIN_API_TOKEN", "secret")
        r = gated_client.get(
            "/api/test/running", headers={"X-Admin-Token": "secret"}
        )
        assert r.status_code == 200
        assert r.json() == {"running": {}}
