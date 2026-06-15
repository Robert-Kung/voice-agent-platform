"""Tests for the backend graph validator (runtime/graph.py).

Covers the structural rule set in parity with the frontend `validateGraph`,
plus the two backend-specific rules:
  - graph + realtime mode is a blocking error (mode coupling)
  - tool_result edge with a non-empty condition is a warning (v1 unconditional)
"""

from runtime.graph import normalize_graph, validate_graph


def _node(nid, ntype="prompt", title="", prompt="", tools=None):
    return {
        "id": nid,
        "type": ntype,
        "title": title or nid,
        "prompt": prompt,
        "tools": tools or [],
        "position": {"x": 0, "y": 0},
    }


def _edge(eid, source, target, trigger=None, condition="", label=None):
    e = {"id": eid, "source": source, "target": target, "condition": condition}
    if trigger is not None:
        e["trigger"] = trigger
    if label is not None:
        e["label"] = label
    return e


def _graph(nodes, edges=None):
    return {"schema_version": 1, "global_prompt": "", "nodes": nodes, "edges": edges or []}


def _codes(issues):
    return {i.code for i in issues}


# ── happy path ─────────────────────────────────────────────────────


def test_minimal_valid_graph():
    g = _graph([_node("start", "start")])
    res = validate_graph(g, available_tools=[])
    assert res.valid
    assert res.errors == []


def test_valid_two_node_flow():
    g = _graph(
        [_node("start", "start"), _node("ticket", "prompt")],
        [_edge("e1", "start", "ticket", condition="需要建單")],
    )
    res = validate_graph(g, available_tools=[])
    assert res.valid


# ── error rules ────────────────────────────────────────────────────


def test_missing_start_is_error():
    res = validate_graph(_graph([_node("a", "prompt")]), available_tools=[])
    assert "no_start" in _codes(res.errors)
    assert not res.valid


def test_multiple_start_is_error():
    res = validate_graph(
        _graph([_node("s1", "start"), _node("s2", "start")]), available_tools=[]
    )
    assert "multiple_start" in _codes(res.errors)


def test_duplicate_node_id_is_error():
    res = validate_graph(
        _graph([_node("start", "start"), _node("start", "prompt")]), available_tools=[]
    )
    assert "duplicate_node_id" in _codes(res.errors)


def test_invalid_node_type_is_error():
    res = validate_graph(_graph([_node("start", "start"), _node("x", "bogus")]), available_tools=[])
    assert "invalid_node_type" in _codes(res.errors)


def test_duplicate_edge_id_is_error():
    g = _graph(
        [_node("start", "start"), _node("a", "prompt")],
        [_edge("e1", "start", "a"), _edge("e1", "start", "a")],
    )
    assert "duplicate_edge_id" in _codes(validate_graph(g, available_tools=[]).errors)


def test_edge_endpoint_missing_is_error():
    g = _graph([_node("start", "start")], [_edge("e1", "start", "ghost")])
    assert "edge_endpoint_missing" in _codes(validate_graph(g, available_tools=[]).errors)


def test_edge_into_start_is_error():
    g = _graph(
        [_node("start", "start"), _node("a", "prompt")],
        [_edge("e1", "start", "a"), _edge("e2", "a", "start")],
    )
    assert "edge_into_start" in _codes(validate_graph(g, available_tools=[]).errors)


def test_edge_out_of_end_is_error():
    g = _graph(
        [_node("start", "start"), _node("done", "end")],
        [_edge("e1", "start", "done"), _edge("e2", "done", "start")],
    )
    codes = _codes(validate_graph(g, available_tools=[]).errors)
    assert "edge_out_of_end" in codes


def test_invalid_trigger_is_error():
    g = _graph(
        [_node("start", "start"), _node("a", "prompt")],
        [_edge("e1", "start", "a", trigger="on_timer")],
    )
    assert "invalid_trigger" in _codes(validate_graph(g, available_tools=[]).errors)


def test_unreachable_node_is_error():
    g = _graph([_node("start", "start"), _node("island", "prompt")])
    assert "unreachable_node" in _codes(validate_graph(g, available_tools=[]).errors)


def test_disconnected_cycle_is_unreachable():
    # A cycle not connected to start must fail reachability, not a mere isolated check.
    g = _graph(
        [_node("start", "start"), _node("a", "prompt"), _node("b", "prompt")],
        [_edge("e1", "a", "b"), _edge("e2", "b", "a")],
    )
    res = validate_graph(g, available_tools=[])
    assert "unreachable_node" in _codes(res.errors)


# ── mode coupling (backend-specific) ───────────────────────────────


def test_graph_realtime_conflict_is_error():
    g = _graph([_node("start", "start")])
    res = validate_graph(g, available_tools=[], mode="realtime")
    assert "graph_realtime_conflict" in _codes(res.errors)
    assert not res.valid


def test_graph_pipeline_mode_allowed():
    g = _graph([_node("start", "start")])
    res = validate_graph(g, available_tools=[], mode="pipeline")
    assert "graph_realtime_conflict" not in _codes(res.errors)
    assert res.valid


def test_mode_none_does_not_flag():
    g = _graph([_node("start", "start")])
    assert validate_graph(g, available_tools=[], mode=None).valid


# ── warning rules (non-blocking) ───────────────────────────────────


def test_tool_result_condition_is_warning_not_error():
    g = _graph(
        [_node("start", "start"), _node("ho", "handoff")],
        [_edge("e1", "start", "ho", trigger="tool_result", condition="建單失敗")],
    )
    res = validate_graph(g, available_tools=[], handoff_enabled=True)
    assert "tool_result_condition" in _codes(res.warnings)
    assert res.valid  # warning does not block


def test_empty_tool_result_condition_no_warning():
    g = _graph(
        [_node("start", "start"), _node("ho", "handoff")],
        [_edge("e1", "start", "ho", trigger="tool_result")],
    )
    res = validate_graph(g, available_tools=[], handoff_enabled=True)
    assert "tool_result_condition" not in _codes(res.warnings)


def test_tool_result_no_domain_tool_is_warning():
    # node sources a tool_result edge but has no domain tool → dead transition.
    g = _graph(
        [_node("start", "start"), _node("ho", "handoff")],
        [_edge("e1", "start", "ho", trigger="tool_result")],
    )
    res = validate_graph(g, available_tools=[], handoff_enabled=True)
    assert "tool_result_no_tool" in _codes(res.warnings)
    assert res.valid  # warning, not blocking


def test_tool_result_with_domain_tool_no_warning():
    g = _graph(
        [_node("start", "start", tools=["create_ticket"]), _node("ho", "handoff")],
        [_edge("e1", "start", "ho", trigger="tool_result")],
    )
    res = validate_graph(g, available_tools=["create_ticket"], handoff_enabled=True)
    assert "tool_result_no_tool" not in _codes(res.warnings)


def test_tool_result_only_auto_mounted_tool_still_warns():
    # lookup_qa is excluded from wrapping, so it does not count as a domain tool.
    g = _graph(
        [_node("start", "start", tools=["lookup_qa"]), _node("ho", "handoff")],
        [_edge("e1", "start", "ho", trigger="tool_result")],
    )
    res = validate_graph(g, available_tools=["get_current_time"], handoff_enabled=True)
    assert "tool_result_no_tool" in _codes(res.warnings)


def test_self_loop_is_warning():
    g = _graph(
        [_node("start", "start"), _node("a", "prompt")],
        [_edge("e0", "start", "a"), _edge("e1", "a", "a", condition="重試")],
    )
    res = validate_graph(g, available_tools=[])
    assert "self_loop" in _codes(res.warnings)
    assert res.valid


def test_ambiguous_unconditional_is_warning():
    g = _graph(
        [_node("start", "start"), _node("a", "prompt"), _node("b", "prompt")],
        [_edge("e1", "start", "a"), _edge("e2", "start", "b")],
    )
    res = validate_graph(g, available_tools=[])
    assert "ambiguous_unconditional" in _codes(res.warnings)


def test_handoff_disabled_is_warning():
    g = _graph(
        [_node("start", "start"), _node("ho", "handoff")],
        [_edge("e1", "start", "ho", condition="轉接")],
    )
    res = validate_graph(g, available_tools=[], handoff_enabled=False)
    assert "handoff_disabled" in _codes(res.warnings)


def test_dangling_tool_is_warning():
    g = _graph([_node("start", "start", tools=["nonexistent_tool"])])
    res = validate_graph(g, available_tools=["get_current_time"], handoff_enabled=False)
    assert "dangling_tool" in _codes(res.warnings)


def test_dangling_tool_skipped_when_builtins_empty():
    g = _graph([_node("start", "start", tools=["whatever"])])
    res = validate_graph(g, available_tools=[])
    assert "dangling_tool" not in _codes(res.warnings)


def test_auto_mounted_tools_are_legal():
    g = _graph([_node("start", "start", tools=["lookup_qa", "transfer_to_human"])])
    res = validate_graph(g, available_tools=["get_current_time"])
    assert "dangling_tool" not in _codes(res.warnings)


# ── normalize_graph (load-boundary) ────────────────────────────────


def test_normalize_fills_missing_fields():
    raw = {"nodes": [{"id": "start", "type": "start"}]}
    g = normalize_graph(raw)
    assert g is not None
    assert g["nodes"][0]["tools"] == []
    assert g["nodes"][0]["position"] == {"x": 0, "y": 0}
    assert g["edges"] == []
    assert g["schema_version"] == 1


def test_normalize_returns_none_for_unusable():
    assert normalize_graph(None) is None
    assert normalize_graph({"nodes": []}) is None
    assert normalize_graph({"nodes": "notalist"}) is None
    assert normalize_graph("string") is None


def test_normalize_then_validate_round_trip():
    raw = {
        "nodes": [{"id": "start", "type": "start"}, {"id": "a", "type": "prompt"}],
        "edges": [{"id": "e1", "source": "start", "target": "a"}],
    }
    g = normalize_graph(raw)
    assert validate_graph(g, available_tools=[]).valid
