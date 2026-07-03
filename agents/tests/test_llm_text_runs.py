"""LLM-backed text test run tests (kind: llm_text) with a scripted fake LLM."""

import asyncio
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from livekit.agents import llm as lkllm
from livekit.agents.types import APIConnectOptions

from api.deps import get_db
from api.main import app
from db.event_sanitizer import REDACTED, sanitize_llm_text
from db.models import Base

import runtime.llm_text_runner as llm_text_runner


# ── Fake LLM ───────────────────────────────────────────────


class FakeLLMStream(lkllm.LLMStream):
    def __init__(self, llm, *, chat_ctx, tools, conn_options, step):
        self._step = step
        super().__init__(llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)

    async def _run(self) -> None:
        step = self._step
        if step.get("sleep"):
            await asyncio.sleep(step["sleep"])
        tool_calls = [
            lkllm.FunctionToolCall(
                type="function",
                name=tc["name"],
                arguments=tc.get("arguments", "{}"),
                call_id=f"call_{i}",
            )
            for i, tc in enumerate(step.get("tool_calls", []))
        ]
        delta = lkllm.ChoiceDelta(
            role="assistant",
            content=step.get("content"),
            tool_calls=tool_calls,
        )
        usage = lkllm.CompletionUsage(completion_tokens=5, prompt_tokens=7, total_tokens=12)
        self._event_ch.send_nowait(lkllm.ChatChunk(id="fake", delta=delta, usage=usage))


class FakeLLM(lkllm.LLM):
    """Scripted LLM: each chat() call consumes the next step.

    Step shapes: {"content": str} or {"tool_calls": [{"name", "arguments"}]}
    or {"sleep": seconds, "content": str} for timeout tests.
    """

    def __init__(self, script):
        super().__init__()
        self.script = list(script)
        self.calls: list[dict] = []

    def chat(self, *, chat_ctx, tools=None, conn_options=None, **kwargs):
        step = self.script.pop(0) if self.script else {"content": "（腳本已盡）"}
        self.calls.append(
            {
                "tool_names": [
                    getattr(getattr(t, "info", None), "name", None)
                    or (t.info.raw_schema or {}).get("name")
                    if hasattr(t, "info")
                    else None
                    for t in (tools or [])
                ],
                "system": next(
                    (i.text_content for i in chat_ctx.items if getattr(i, "role", None) == "system"),
                    "",
                ),
            }
        )
        return FakeLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=APIConnectOptions(max_retry=0, timeout=5.0),
            step=step,
        )


def _patch_fake_llm(monkeypatch, script, fallback_reason=None):
    fake = FakeLLM(script)

    def _resolve(config):
        return fake, [{"provider": "fake", "model": "fake-1"}], fallback_reason

    monkeypatch.setattr(llm_text_runner, "resolve_text_test_llm", _resolve)
    return fake


# ── Fixtures ───────────────────────────────────────────────


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


def _create_profile(client: TestClient, *, config: dict | None = None) -> str:
    response = client.post(
        "/api/profiles",
        json={
            "name": "llm_text_profile",
            "display_name": "LLM Text Profile",
            "config": config or {"instructions": "你是測試客服。", "tools": []},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _post_llm_text(client, profile_id, **payload):
    body = {"kind": "llm_text", **payload}
    return client.post(f"/api/profiles/{profile_id}/test-runs", json=body)


def _event_types(data):
    return [event["event_type"] for event in data["events"]]


# ── Prompt mode ────────────────────────────────────────────


def test_llm_text_prompt_run_records_response_and_usage(client, monkeypatch):
    fake = _patch_fake_llm(monkeypatch, [{"content": "我們營業到晚上九點。"}])
    profile_id = _create_profile(client)

    response = _post_llm_text(client, profile_id, message="請問營業時間？")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["kind"] == "llm_text"
    assert data["status"] == "completed"
    assert data["final_summary"]["assistant_output"] == "我們營業到晚上九點。"
    assert data["final_summary"]["usage"]["llm_calls"] == 1
    assert data["final_summary"]["usage"]["total_tokens"] == 12
    types = _event_types(data)
    assert types[0] == "test_started"
    assert "llm_response" in types
    assert "token_usage" in types
    assert types[-1] == "test_completed"
    # system instructions came from the shared prompt composer
    assert "你是測試客服。" in fake.calls[0]["system"]


def test_llm_text_multi_turn_messages(client, monkeypatch):
    _patch_fake_llm(monkeypatch, [{"content": "第一輪回覆"}, {"content": "第二輪回覆"}])
    profile_id = _create_profile(client)

    response = _post_llm_text(client, profile_id, messages=["你好", "營業時間？"])

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert data["user_messages"] == ["你好", "營業時間？"]
    assert data["final_summary"]["turns"] == 2
    assert data["final_summary"]["assistant_output"] == "第二輪回覆"
    replies = [e for e in data["events"] if e["event_type"] == "llm_response"]
    assert [r["payload"]["turn"] for r in replies] == [1, 2]


def test_llm_text_tool_call_feeds_dry_run_result_back(client, monkeypatch):
    _patch_fake_llm(
        monkeypatch,
        [
            {"tool_calls": [{"name": "create_ticket", "arguments": '{"summary": "電梯壞了"}'}]},
            {"content": "已為您記錄單據。"},
        ],
    )
    profile_id = _create_profile(
        client,
        config={
            "instructions": "客服",
            "tools": [
                {
                    "name": "create_ticket",
                    "description": "建單",
                    "endpoint": "https://example.com/tickets",
                    "parameters": [{"name": "summary", "type": "string", "required": True}],
                }
            ],
        },
    )

    response = _post_llm_text(client, profile_id, message="電梯壞了")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    types = _event_types(data)
    assert "tool_call" in types
    assert "tool_result" in types
    tool_event = next(e for e in data["events"] if e["event_type"] == "tool_call")
    assert tool_event["payload"]["mode"] == "dry_run"
    assert tool_event["payload"]["executed"] is False
    assert tool_event["payload"]["arguments"] == {"summary": "電梯壞了"}
    assert data["final_summary"]["assistant_output"] == "已為您記錄單據。"


def test_llm_text_max_steps_guard(client, monkeypatch):
    # LLM keeps calling tools forever; runner must stop at max_steps.
    _patch_fake_llm(
        monkeypatch,
        [{"tool_calls": [{"name": "get_current_time"}]}] * 20,
    )
    profile_id = _create_profile(
        client,
        config={"instructions": "客服", "tools": [{"name": "get_current_time"}]},
    )

    response = _post_llm_text(client, profile_id, message="現在幾點？")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert "max_steps_reached" in _event_types(data)


def test_llm_text_turn_timeout_marks_run_failed(client, monkeypatch):
    _patch_fake_llm(monkeypatch, [{"sleep": 0.5, "content": "太慢了"}])
    monkeypatch.setattr(llm_text_runner, "TURN_TIMEOUT_SECONDS", 0.05)
    profile_id = _create_profile(client)

    response = _post_llm_text(client, profile_id, message="hi")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "failed"
    types = _event_types(data)
    assert "runner_error" in types
    assert data["events"][-1]["payload"]["status"] == "failed"


def test_llm_text_realtime_profile_falls_back_with_warning(client, monkeypatch):
    _patch_fake_llm(
        monkeypatch,
        [{"content": "realtime fallback 回覆"}],
        fallback_reason="realtime_text_fallback",
    )
    profile_id = _create_profile(
        client,
        config={"instructions": "客服", "models": {"mode": "realtime"}, "tools": []},
    )

    response = _post_llm_text(client, profile_id, message="hi")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    fallback = next(e for e in data["events"] if e["event_type"] == "llm_fallback")
    assert fallback["severity"] == "warning"
    assert fallback["payload"]["reason"] == "realtime_text_fallback"
    assert data["final_summary"]["llm_fallback"] == "realtime_text_fallback"


# ── Graph mode ─────────────────────────────────────────────


def _graph_profile_config(graph, tools=None):
    return {
        "instructions": "fallback",
        "editor_mode": "graph",
        "models": {"mode": "pipeline"},
        "graph": graph,
        "tools": tools or [],
    }


def test_llm_text_graph_goto_tool_routes_to_target_node(client, monkeypatch):
    _patch_fake_llm(
        monkeypatch,
        [
            {"tool_calls": [{"name": "goto_info"}]},
            {"content": "這裡是資訊節點的回覆。"},
        ],
    )
    graph = {
        "schema_version": 1,
        "nodes": [
            {"id": "start", "type": "start", "title": "入口", "prompt": "分流", "tools": [], "position": {"x": 0, "y": 0}},
            {"id": "info", "type": "prompt", "title": "資訊", "prompt": "提供資訊", "tools": [], "position": {"x": 200, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "info", "trigger": "user_turn", "condition": "使用者詢問資訊"}
        ],
    }
    profile_id = _create_profile(client, config=_graph_profile_config(graph))

    response = _post_llm_text(client, profile_id, message="我要查資訊")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    types = _event_types(data)
    assert "graph_validated" in types
    edge = next(e for e in data["events"] if e["event_type"] == "edge_selected")
    assert edge["payload"]["trigger"] == "user_turn"
    assert edge["payload"]["target"] == "info"
    entered = [e["payload"]["node_id"] for e in data["events"] if e["event_type"] == "node_entered"]
    assert entered == ["start", "info"]
    assert data["final_summary"]["graph_path"] == ["start", "info"]
    assert data["final_summary"]["assistant_output"] == "這裡是資訊節點的回覆。"


def test_llm_text_graph_tool_result_transitions_unconditionally_to_handoff(client, monkeypatch):
    fake = _patch_fake_llm(
        monkeypatch,
        [{"tool_calls": [{"name": "create_ticket", "arguments": '{"summary": "電梯壞了"}'}]}],
    )
    graph = {
        "schema_version": 1,
        "nodes": [
            {"id": "start", "type": "start", "title": "入口", "prompt": "詢問故障", "tools": ["create_ticket"], "position": {"x": 0, "y": 0}},
            {"id": "handoff", "type": "handoff", "title": "真人", "prompt": "轉真人", "tools": [], "position": {"x": 200, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "handoff", "trigger": "tool_result", "condition": ""}
        ],
    }
    profile_id = _create_profile(
        client,
        config={
            **_graph_profile_config(
                graph,
                tools=[{"name": "create_ticket", "endpoint": "https://example.com/tickets"}],
            ),
            "human_operator": {"enabled": True},
        },
    )

    response = _post_llm_text(client, profile_id, message="電梯壞了")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    types = _event_types(data)
    assert "tool_result" in types
    assert "handoff" in types
    edge = next(e for e in data["events"] if e["event_type"] == "edge_selected")
    assert edge["payload"]["trigger"] == "tool_result"
    assert data["final_summary"]["termination_reason"] == "handoff"
    assert data["final_summary"]["graph_path"] == ["start", "handoff"]
    # transition is runner-driven: only one LLM call was needed
    assert len(fake.calls) == 1


def test_llm_text_graph_tool_result_prompt_target_speaks_with_result_in_context(client, monkeypatch):
    """tool_result edge: source node does not reply; the TARGET node generates
    the reply with the dry-run tool result already in chat context."""
    fake = _patch_fake_llm(
        monkeypatch,
        [
            {"tool_calls": [{"name": "create_ticket", "arguments": '{"summary": "電梯壞了"}'}]},
            {"content": "已建單，這是後續說明。"},
        ],
    )
    graph = {
        "schema_version": 1,
        "nodes": [
            {"id": "start", "type": "start", "title": "入口", "prompt": "詢問故障", "tools": ["create_ticket"], "position": {"x": 0, "y": 0}},
            {"id": "confirm", "type": "prompt", "title": "建單確認", "prompt": "向使用者確認單據內容與後續流程", "tools": [], "position": {"x": 200, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "confirm", "trigger": "tool_result", "condition": ""}
        ],
    }
    profile_id = _create_profile(
        client,
        config=_graph_profile_config(
            graph,
            tools=[{"name": "create_ticket", "endpoint": "https://example.com/tickets"}],
        ),
    )

    response = _post_llm_text(client, profile_id, message="電梯壞了")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert data["final_summary"]["graph_path"] == ["start", "confirm"]
    replies = [e for e in data["events"] if e["event_type"] == "llm_response"]
    assert len(replies) == 1
    assert replies[0]["payload"]["node_id"] == "confirm"
    # second LLM call ran with the TARGET node's instructions
    assert len(fake.calls) == 2
    assert "向使用者確認單據內容與後續流程" in fake.calls[1]["system"]


def test_llm_text_graph_mixed_chunk_domain_tool_runs_before_transition(client, monkeypatch):
    """Same-chunk [goto, domain tool]: domain tool executes in SOURCE node
    context first, then exactly one transition to the goto target is applied."""
    fake = _patch_fake_llm(
        monkeypatch,
        [
            {
                "tool_calls": [
                    {"name": "goto_info", "arguments": "{}"},
                    {"name": "get_current_time", "arguments": "{}"},
                ]
            },
            {"content": "這裡是資訊節點的回覆。"},
        ],
    )
    graph = {
        "schema_version": 1,
        "nodes": [
            {"id": "start", "type": "start", "title": "入口", "prompt": "分流", "tools": ["get_current_time"], "position": {"x": 0, "y": 0}},
            {"id": "info", "type": "prompt", "title": "資訊", "prompt": "提供資訊", "tools": [], "position": {"x": 200, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "info", "trigger": "user_turn", "condition": "使用者詢問資訊"}
        ],
    }
    profile_id = _create_profile(
        client,
        config=_graph_profile_config(graph, tools=[{"name": "get_current_time"}]),
    )

    response = _post_llm_text(client, profile_id, message="現在幾點？我要查資訊")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    # exactly one transition, no duplicate entries
    assert data["final_summary"]["graph_path"] == ["start", "info"]
    edges = [e for e in data["events"] if e["event_type"] == "edge_selected"]
    assert len(edges) == 1
    assert edges[0]["payload"]["trigger"] == "user_turn"
    # domain tool dispatched before the transition (source node context)
    tool_seq = next(e["seq"] for e in data["events"] if e["event_type"] == "tool_call")
    info_entered_seq = next(
        e["seq"]
        for e in data["events"]
        if e["event_type"] == "node_entered" and e["payload"]["node_id"] == "info"
    )
    assert tool_seq < info_entered_seq
    assert len(fake.calls) == 2


def test_llm_text_graph_invalid_falls_back_to_prompt_mode(client, monkeypatch):
    _patch_fake_llm(monkeypatch, [{"content": "prompt fallback 回覆"}])
    profile_id = _create_profile(
        client,
        config={
            "instructions": "fallback",
            "editor_mode": "graph",
            "models": {"mode": "pipeline"},
            "tools": [],
        },
    )

    response = _post_llm_text(client, profile_id, message="hi")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    fallback = next(e for e in data["events"] if e["event_type"] == "fallback")
    assert fallback["payload"]["reason"] == "graph_missing_or_unusable"
    assert "prompt_rendered" in _event_types(data)


# ── API contract ───────────────────────────────────────────


def test_test_run_request_requires_message_or_messages(client):
    profile_id = _create_profile(client)
    response = client.post(f"/api/profiles/{profile_id}/test-runs", json={"kind": "llm_text"})
    assert response.status_code == 422


def test_flow_runs_default_kind_and_list_kind_filter(client, monkeypatch):
    _patch_fake_llm(monkeypatch, [{"content": "llm 回覆"}])
    profile_id = _create_profile(client)

    flow = client.post(f"/api/profiles/{profile_id}/test-runs", json={"message": "flow 測試"})
    assert flow.status_code == 201, flow.text
    assert flow.json()["kind"] == "flow"

    llm_run = _post_llm_text(client, profile_id, message="llm 測試")
    assert llm_run.status_code == 201, llm_run.text

    all_rows = client.get(f"/api/profiles/{profile_id}/test-runs")
    assert all_rows.headers["X-Total-Count"] == "2"

    llm_rows = client.get(f"/api/profiles/{profile_id}/test-runs?kind=llm_text")
    assert llm_rows.headers["X-Total-Count"] == "1"
    assert [r["kind"] for r in llm_rows.json()] == ["llm_text"]

    flow_rows = client.get(f"/api/profiles/{profile_id}/test-runs?kind=flow")
    assert flow_rows.headers["X-Total-Count"] == "1"
    assert [r["kind"] for r in flow_rows.json()] == ["flow"]


# ── Sanitizer ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expect_redacted",
    [
        ("請設定 LIVEKIT_API_KEY=abc123 後重試", True),
        ("Authorization: Bearer sk-abcdef123456", True),
        ("請造訪 https://example.com/page?token=secret123 查看", True),
        ("您的 token 已經寄出，請至信箱查收。", False),
        ("我們營業到晚上九點。", False),
    ],
)
def test_sanitize_llm_text_redacts_credentials_but_keeps_prose(text, expect_redacted):
    sanitized = sanitize_llm_text(text)
    if expect_redacted:
        assert REDACTED in sanitized
        assert "abc123" not in sanitized
        assert "sk-abcdef123456" not in sanitized
        assert "token=secret123" not in sanitized
    else:
        assert sanitized == text


# ── Integration (gated) ────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("LLM_TEXT_TEST_INTEGRATION") != "1",
    reason="set LLM_TEXT_TEST_INTEGRATION=1 to run against a real LLM",
)
def test_llm_text_integration_real_llm(client):
    profile_id = _create_profile(client)
    response = _post_llm_text(client, profile_id, message="請用一句話介紹你自己。")
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert data["final_summary"]["assistant_output"]
    assert data["final_summary"]["usage"]["total_tokens"] > 0
