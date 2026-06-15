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

    def test_graph_config_roundtrips_intact(self, client):
        # graph-agent-builder: config is free-form JSON, so the graph block +
        # editor_mode must round-trip with no migration and no field loss.
        graph = {
            "schema_version": 1,
            "global_prompt": "使用繁體中文",
            "nodes": [
                {
                    "id": "start",
                    "type": "start",
                    "title": "接聽",
                    "prompt": "打招呼",
                    "tools": ["create_ticket"],
                    "position": {"x": 80, "y": 160},
                },
                {
                    "id": "transfer",
                    "type": "handoff",
                    "title": "轉接",
                    "prompt": "",
                    "tools": [],
                    "position": {"x": 480, "y": 160},
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "start",
                    "target": "transfer",
                    "trigger": "tool_result",
                    "condition": "建單失敗",
                    "label": "失敗轉接",
                }
            ],
        }
        r = client.post("/api/profiles", json={
            "name": "graph_roundtrip",
            "display_name": "Graph RT",
            "config": {
                "instructions": "fallback flatten",
                "editor_mode": "graph",
                "graph": graph,
                "tools": [],
            },
        })
        assert r.status_code == 201
        profile_id = r.json()["id"]

        r = client.get(f"/api/profiles/{profile_id}")
        assert r.status_code == 200
        config = r.json()["config"]
        assert config["editor_mode"] == "graph"
        assert config["graph"] == graph
        assert config["graph"]["schema_version"] == 1


class TestGraphSaveValidation:
    """graph-runtime-validation: backend hard validation on graph-mode saves."""

    @staticmethod
    def _start_only_graph(extra_nodes=None, edges=None):
        nodes = [
            {"id": "start", "type": "start", "title": "入口", "prompt": "打招呼",
             "tools": [], "position": {"x": 0, "y": 0}},
        ]
        nodes.extend(extra_nodes or [])
        return {"schema_version": 1, "global_prompt": "", "nodes": nodes, "edges": edges or []}

    def test_invalid_graph_save_422(self, client):
        # No start node → blocking structural error.
        bad_graph = {
            "schema_version": 1, "global_prompt": "", "edges": [],
            "nodes": [{"id": "a", "type": "prompt", "title": "A", "prompt": "",
                       "tools": [], "position": {"x": 0, "y": 0}}],
        }
        r = client.post("/api/profiles", json={
            "name": "bad_graph", "display_name": "Bad",
            "config": {"instructions": "fb", "editor_mode": "graph", "graph": bad_graph, "tools": []},
        })
        assert r.status_code == 422
        codes = {e["code"] for e in r.json()["detail"]["errors"]}
        assert "no_start" in codes

    def test_graph_realtime_conflict_422(self, client):
        r = client.post("/api/profiles", json={
            "name": "graph_rt", "display_name": "GraphRT",
            "config": {
                "instructions": "fb", "editor_mode": "graph",
                "graph": self._start_only_graph(),
                "models": {"mode": "realtime"}, "tools": [],
            },
        })
        assert r.status_code == 422
        codes = {e["code"] for e in r.json()["detail"]["errors"]}
        assert "graph_realtime_conflict" in codes

    def test_valid_graph_pipeline_saves(self, client):
        r = client.post("/api/profiles", json={
            "name": "graph_pipe", "display_name": "GraphPipe",
            "config": {
                "instructions": "fb", "editor_mode": "graph",
                "graph": self._start_only_graph(),
                "models": {"mode": "pipeline"}, "tools": [],
            },
        })
        assert r.status_code == 201

    def test_prompt_mode_save_bypasses_graph_validation(self, client):
        # editor_mode absent (prompt): even a structurally broken graph block is
        # not validated — it is retained but inert.
        r = client.post("/api/profiles", json={
            "name": "prompt_mode", "display_name": "Prompt",
            "config": {
                "instructions": "hi", "tools": [],
                "graph": {"nodes": [{"id": "a", "type": "prompt"}]},  # no start, but prompt mode
            },
        })
        assert r.status_code == 201

    def test_update_to_invalid_graph_422(self, client):
        r = client.post("/api/profiles", json={"name": "upd_graph", "display_name": "U"})
        pid = r.json()["id"]
        r = client.patch(f"/api/profiles/{pid}", json={
            "config": {
                "instructions": "fb", "editor_mode": "graph",
                "graph": self._start_only_graph(), "models": {"mode": "realtime"},
            },
        })
        assert r.status_code == 422


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


class TestModelsBlockValidation:
    """5.7: profile save validates the optional `models` block shape (422 on bad)."""

    def test_valid_models_block_accepted(self, client):
        r = client.post("/api/profiles", json={
            "name": "mv_ok", "display_name": "OK",
            "config": {"models": {"mode": "pipeline", "llm": [{"provider": "google", "model": "gemini-2.5-flash"}]}},
        })
        assert r.status_code == 201, r.text

    def test_unknown_direct_provider_rejected(self, client):
        r = client.post("/api/profiles", json={
            "name": "mv_bad_direct", "display_name": "Bad",
            "config": {"models": {"llm": [{"provider": "cartesia", "model": "x", "via": "direct"}]}},
        })
        assert r.status_code == 422, r.text

    def test_bad_mode_rejected(self, client):
        r = client.post("/api/profiles", json={
            "name": "mv_bad_mode", "display_name": "Bad",
            "config": {"models": {"mode": "banana"}},
        })
        assert r.status_code == 422, r.text

    def test_dead_realtime_variant_rejected(self, client):
        r = client.post("/api/profiles", json={
            "name": "mv_dead_rt", "display_name": "Bad",
            "config": {"models": {"realtime": {"model": "gemini-3.1-flash-live-preview"}}},
        })
        assert r.status_code == 422, r.text

    def test_patch_with_bad_models_rejected(self, client):
        client.post("/api/profiles", json={"name": "mv_patch", "display_name": "P"})
        got = client.get("/api/profiles")
        pid = next(p["id"] for p in got.json() if p["name"] == "mv_patch")
        r = client.patch(f"/api/profiles/{pid}", json={
            "config": {"models": {"stt": [{"provider": "elevenlabs", "model": "x", "via": "direct"}]}},
        })
        assert r.status_code == 422, r.text

    def test_config_without_models_still_free_form(self, client):
        r = client.post("/api/profiles", json={
            "name": "mv_free", "display_name": "Free",
            "config": {"anything": {"nested": [1, 2, 3]}, "qa_mode": "inline"},
        })
        assert r.status_code == 201, r.text
