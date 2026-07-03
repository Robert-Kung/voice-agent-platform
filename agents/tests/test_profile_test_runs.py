"""Profile text test run API and store tests."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.deps import get_db
from api.main import app
from db.event_sanitizer import REDACTED, SCHEMA_VERSION, sanitize_event_payload
from db.models import Base


@pytest.fixture()
def client(monkeypatch):
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


@pytest.fixture()
def secured_client():
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


def _create_profile(client: TestClient, *, config: dict | None = None) -> str:
    response = client.post(
        "/api/profiles",
        json={
            "name": "test_profile",
            "display_name": "Test Profile",
            "config": config or {"instructions": "你是測試客服。", "tools": []},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_prompt_text_run_records_ordered_events_and_summary(client):
    profile_id = _create_profile(client)

    response = client.post(
        f"/api/profiles/{profile_id}/test-runs",
        json={"message": "請問營業時間？"},
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["profile_id"] == profile_id
    assert data["status"] == "completed"
    assert data["tool_execution_mode"] == "dry_run"
    assert data["profile_config_hash"]
    assert data["profile_snapshot_at"]
    assert data["final_summary"]["status"] == "completed"
    seqs = [event["seq"] for event in data["events"]]
    assert seqs == sorted(seqs)
    assert seqs == list(range(1, len(seqs) + 1))
    event_types = [event["event_type"] for event in data["events"]]
    assert event_types[0] == "test_started"
    assert "prompt_rendered" in event_types
    assert "assistant_output" in event_types
    assert event_types[-1] == "test_completed"
    assert data["events"][-1]["payload"]["status"] == "completed"
    assert all(event["payload"]["schema_version"] == SCHEMA_VERSION for event in data["events"])


def test_list_and_get_profile_test_runs_with_total_header(client):
    profile_id = _create_profile(client)
    first = client.post(f"/api/profiles/{profile_id}/test-runs", json={"message": "第一筆"}).json()
    second = client.post(f"/api/profiles/{profile_id}/test-runs", json={"message": "第二筆"}).json()

    response = client.get(f"/api/profiles/{profile_id}/test-runs?limit=1&offset=0")

    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "2"
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["id"] in {first["id"], second["id"]}

    detail = client.get(f"/api/profiles/{profile_id}/test-runs/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == first["id"]
    assert detail.json()["events"]


def test_profile_test_run_endpoints_require_admin_when_token_set(secured_client):
    response = secured_client.post(
        "/api/profiles",
        json={"name": "secured_profile", "display_name": "Secured"},
        headers={"X-Admin-Token": "test-secret-token"},
    )
    assert response.status_code == 201
    profile_id = response.json()["id"]

    assert secured_client.post(
        f"/api/profiles/{profile_id}/test-runs",
        json={"message": "hi"},
    ).status_code == 401
    assert secured_client.get(f"/api/profiles/{profile_id}/test-runs").status_code == 401

    ok = secured_client.post(
        f"/api/profiles/{profile_id}/test-runs",
        json={"message": "hi"},
        headers={"X-Admin-Token": "test-secret-token"},
    )
    assert ok.status_code == 201


@pytest.mark.parametrize(
    "payload",
    [
        {"headers": {"Authorization": "Bearer secret", "X-Api-Key": "abc"}},
        {"query": {"token": "abc", "normal": "ok"}},
        {"nested": {"password": "pw", "secret_value": "sv"}},
        {"env": {"LIVEKIT_API_KEY": "secret", "DATABASE_URL": "sqlite:///secret"}},
        {"endpoint": "https://example.com/tickets?token=secret&normal=ok"},
    ],
)
def test_sanitizer_redacts_sensitive_payload_values(payload):
    sanitized = sanitize_event_payload(payload)
    text = str(sanitized)
    assert "Bearer" not in text
    assert "Bearer secret" not in text
    assert "sqlite:///secret" not in text
    assert "abc" not in text or "normal" in text
    assert "pw" not in text
    assert "sv" not in text
    assert "token=secret" not in text
    assert REDACTED in text
    assert sanitized["schema_version"] == SCHEMA_VERSION


def test_dry_run_tool_does_not_execute_external_http_tool(client):
    profile_id = _create_profile(
        client,
        config={
            "instructions": "測試工具",
            "tools": [
                {
                    "name": "create_ticket",
                    "description": "建單",
                    "endpoint": "https://example.com/tickets?token=secret",
                    "method": "POST",
                    "auth_header": "Bearer ${LIVEKIT_API_KEY}",
                    "timeout_seconds": 7,
                    "parameters": [{"name": "summary", "type": "string", "required": True}],
                }
            ],
        },
    )

    response = client.post(
        f"/api/profiles/{profile_id}/test-runs",
        json={"message": "請建單", "tool_execution_mode": "dry_run"},
    )

    assert response.status_code == 201, response.text
    tool_events = [event for event in response.json()["events"] if event["event_type"] == "tool_call"]
    assert len(tool_events) == 1
    payload = tool_events[0]["payload"]
    assert payload["mode"] == "dry_run"
    assert payload["executed"] is False
    assert payload["timeout_seconds"] == 7
    assert payload["timed_out"] is False
    assert payload["tool_config"]["endpoint"] == "https://example.com/tickets?token=<redacted>"
    assert "auth_header" not in payload["tool_config"]


def test_live_mode_records_live_tool_metadata_without_external_call(client):
    profile_id = _create_profile(
        client,
        config={
            "instructions": "測試工具",
            "tools": [{"name": "get_current_time", "config": {"timezone": "Asia/Taipei"}}],
        },
    )

    response = client.post(
        f"/api/profiles/{profile_id}/test-runs",
        json={"message": "現在幾點？", "tool_execution_mode": "live"},
    )

    assert response.status_code == 201, response.text
    tool_event = next(event for event in response.json()["events"] if event["event_type"] == "tool_call")
    payload = tool_event["payload"]
    assert payload["mode"] == "live"
    assert payload["executed"] is False
    assert payload["result"]["success"] is False
    assert "not enabled" in payload["result"]["error"]


def test_graph_text_run_records_tool_result_transition_and_handoff(client):
    graph = {
        "schema_version": SCHEMA_VERSION,
        "global_prompt": "全程使用繁體中文",
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "title": "入口",
                "prompt": "詢問故障",
                "tools": ["create_ticket"],
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "handoff",
                "type": "handoff",
                "title": "真人",
                "prompt": "轉真人",
                "tools": [],
                "position": {"x": 200, "y": 0},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source": "start",
                "target": "handoff",
                "trigger": "tool_result",
                "condition": "",
            }
        ],
    }
    profile_id = _create_profile(
        client,
        config={
            "instructions": "fallback",
            "editor_mode": "graph",
            "models": {"mode": "pipeline"},
            "human_operator": {"enabled": True},
            "graph": graph,
            "tools": [{"name": "create_ticket", "endpoint": "https://example.com/tickets"}],
        },
    )

    response = client.post(f"/api/profiles/{profile_id}/test-runs", json={"message": "電梯壞了"})

    assert response.status_code == 201, response.text
    event_types = [event["event_type"] for event in response.json()["events"]]
    assert "graph_validated" in event_types
    assert "node_entered" in event_types
    assert "tool_result" in event_types
    assert "edge_selected" in event_types
    assert "handoff" in event_types
    edge = next(event for event in response.json()["events"] if event["event_type"] == "edge_selected")
    assert edge["payload"]["trigger"] == "tool_result"


def test_graph_text_run_records_user_turn_transition(client):
    graph = {
        "schema_version": SCHEMA_VERSION,
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "title": "入口",
                "prompt": "分流",
                "tools": [],
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "info",
                "type": "prompt",
                "title": "資訊",
                "prompt": "提供資訊",
                "tools": [],
                "position": {"x": 200, "y": 0},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source": "start",
                "target": "info",
                "trigger": "user_turn",
                "condition": "使用者詢問資訊",
            }
        ],
    }
    profile_id = _create_profile(
        client,
        config={
            "instructions": "fallback",
            "editor_mode": "graph",
            "models": {"mode": "pipeline"},
            "graph": graph,
            "tools": [],
        },
    )

    response = client.post(f"/api/profiles/{profile_id}/test-runs", json={"message": "我要查資訊"})

    assert response.status_code == 201, response.text
    edge = next(event for event in response.json()["events"] if event["event_type"] == "edge_selected")
    assert edge["payload"]["trigger"] == "user_turn"
    entered = [event for event in response.json()["events"] if event["event_type"] == "node_entered"]
    assert [event["payload"]["node_id"] for event in entered] == ["start", "info"]


def test_graph_missing_block_records_fallback_warning(client):
    profile_id = _create_profile(
        client,
        config={
            "instructions": "fallback",
            "editor_mode": "graph",
            "models": {"mode": "pipeline"},
            "tools": [],
        },
    )

    response = client.post(f"/api/profiles/{profile_id}/test-runs", json={"message": "hi"})

    assert response.status_code == 201, response.text
    fallback = next(event for event in response.json()["events"] if event["event_type"] == "fallback")
    assert fallback["severity"] == "warning"
    assert fallback["payload"]["reason"] == "graph_missing_or_unusable"
