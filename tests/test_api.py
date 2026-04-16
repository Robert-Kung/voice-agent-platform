"""Smoke tests for the Management API."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from api.deps import get_db
from db.models import Base


@pytest.fixture()
def client():
    """Create a TestClient with an in-memory DB override (StaticPool shares connection)."""
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


class TestStatsAPI:
    def test_profile_stats_empty(self, client):
        r = client.get("/api/stats/profiles")
        assert r.status_code == 200
        assert r.json() == []

    def test_daily_stats_empty(self, client):
        r = client.get("/api/stats/daily")
        assert r.status_code == 200
        assert r.json() == []
