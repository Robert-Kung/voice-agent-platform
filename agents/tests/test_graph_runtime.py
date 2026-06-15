"""Tests for graph execution assembly + the strategy-source gate (agent_factory).

The live handoff behavior (SDK actually switching agents mid-call) needs a running
LiveKit session and is covered by the browser e2e (tasks.md 5.2). Here we test the
pure assembly: node→Agent mapping, tool mounting, transition tool wiring, tool_result
wrapping, and the gate's graph-vs-fallback decision.
"""

import asyncio

from agent_factory import (
    build_root_agent,
    build_graph_root_agent,
    _compose_global_preamble,
    _select_graph_strategy,
    _transition_tool_name,
)
from runtime.graph import normalize_graph


def _graph_profile(**overrides):
    profile = {
        "name": "elevator_test",
        "welcome_message": "您好",
        "editor_mode": "graph",
        "tools": [{"name": "get_current_time"}],
        "human_operator": {"enabled": True},
        "models": {"mode": "pipeline"},
        "graph": {
            "schema_version": 1,
            "global_prompt": "全程使用繁體中文",
            "nodes": [
                {"id": "start", "type": "start", "title": "入口", "prompt": "打招呼並詢問需求",
                 "tools": ["get_current_time"], "position": {"x": 0, "y": 0}},
                {"id": "info", "type": "prompt", "title": "說明", "prompt": "提供資訊",
                 "tools": [], "position": {"x": 1, "y": 0}},
                {"id": "ho", "type": "handoff", "title": "轉接", "prompt": "為您轉接真人",
                 "tools": [], "position": {"x": 2, "y": 0}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "info",
                 "trigger": "user_turn", "condition": "需要說明"},
                {"id": "e2", "source": "start", "target": "ho",
                 "trigger": "tool_result", "condition": ""},
            ],
        },
    }
    profile.update(overrides)
    return profile


def _tool_names(agent):
    return {t.info.name for t in agent.tools}


def _tool_by_name(agent, name):
    return next(t for t in agent.tools if t.info.name == name)


def _call(tool, agent, **kwargs):
    """Invoke a node tool's underlying coroutine synchronously."""
    return asyncio.run(tool._func(agent, **kwargs))


# ── pure helpers ───────────────────────────────────────────────────


def test_transition_tool_name_is_schema_safe():
    assert _transition_tool_name("node-1") == "goto_node_1"
    assert _transition_tool_name("ho") == "goto_ho"


def test_compose_global_preamble_includes_global_prompt_and_qa():
    profile = _graph_profile(qa_mode="inline",
                             qa_data=[{"keywords": ["費用"], "answer": "免費"}])
    preamble = _compose_global_preamble(profile, profile["graph"])
    assert "全程使用繁體中文" in preamble
    assert "免費" in preamble  # QA injected at global level


# ── assembly ───────────────────────────────────────────────────────


def test_build_graph_returns_start_node_agent():
    profile = _graph_profile()
    root = build_graph_root_agent(profile, "pipeline", normalize_graph(profile["graph"]))
    # start node instructions carry global preamble + the start node's own prompt
    assert "全程使用繁體中文" in root.instructions
    assert "打招呼並詢問需求" in root.instructions


def test_start_node_has_domain_and_user_turn_transition_tools():
    profile = _graph_profile()
    root = build_graph_root_agent(profile, "pipeline", normalize_graph(profile["graph"]))
    names = _tool_names(root)
    assert "get_current_time" in names          # declared domain tool
    assert "goto_info" in names                 # user_turn edge → transition tool


def test_user_turn_transition_tool_hands_off_to_target():
    profile = _graph_profile()
    # drop the tool_result edge so get_current_time is not wrapped for this test
    profile["graph"]["edges"] = [profile["graph"]["edges"][0]]
    root = build_graph_root_agent(profile, "pipeline", normalize_graph(profile["graph"]))
    goto = _tool_by_name(root, "goto_info")
    target = _call(goto, root)
    assert "提供資訊" in target.instructions      # handed off to the 'info' node Agent


def test_tool_result_wraps_domain_tool_to_return_tuple():
    profile = _graph_profile()
    root = build_graph_root_agent(profile, "pipeline", normalize_graph(profile["graph"]))
    # start has a tool_result edge → its get_current_time is wrapped to (result, agent)
    wrapped = _tool_by_name(root, "get_current_time")
    out = _call(wrapped, root)
    assert isinstance(out, tuple) and len(out) == 2
    result, handoff_agent = out
    assert "current_time" in result               # original tool result preserved
    assert "為您轉接真人" in handoff_agent.instructions  # hands off to the 'ho' node


def test_handoff_node_mounts_transfer_to_human():
    profile = _graph_profile()
    root = build_graph_root_agent(profile, "pipeline", normalize_graph(profile["graph"]))
    # reach the ho node via the registry by following the tool_result handoff
    wrapped = _tool_by_name(root, "get_current_time")
    _, ho_agent = _call(wrapped, root)
    assert "transfer_to_human" in _tool_names(ho_agent)


# ── strategy-source gate ───────────────────────────────────────────


def test_gate_selects_graph_for_valid_pipeline_profile():
    use_graph, reason = _select_graph_strategy(_graph_profile(), "pipeline")
    assert use_graph is True
    assert reason == "ok"


def test_gate_falls_back_for_prompt_mode():
    profile = _graph_profile(editor_mode="prompt")
    use_graph, reason = _select_graph_strategy(profile, "pipeline")
    assert use_graph is False
    assert "editor_mode" in reason


def test_gate_falls_back_under_realtime():
    use_graph, reason = _select_graph_strategy(_graph_profile(), "realtime")
    assert use_graph is False
    assert "pipeline" in reason


def test_gate_falls_back_for_invalid_graph():
    profile = _graph_profile()
    # remove the start node → structurally invalid
    profile["graph"]["nodes"] = [n for n in profile["graph"]["nodes"] if n["type"] != "start"]
    use_graph, reason = _select_graph_strategy(profile, "pipeline")
    assert use_graph is False
    assert "validation failed" in reason


def test_build_root_agent_graph_path_returns_node_agent():
    root = build_root_agent(_graph_profile(), "pipeline")
    assert "goto_info" in _tool_names(root)        # graph path: transition tools present


def test_build_root_agent_fallback_path_is_single_instructions():
    # prompt-mode profile → no transition tools, plain instructions agent
    profile = {"name": "plain", "instructions": "你好", "editor_mode": "prompt"}
    root = build_root_agent(profile, "pipeline")
    assert not any(n.startswith("goto_") for n in _tool_names(root))
