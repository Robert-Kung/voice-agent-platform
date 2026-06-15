"""Backend graph validator + load-boundary normalizer (graph-runtime-validation spec).

This module is the authoritative structural check for both the runtime execution
gate and API save-time hard validation. The frontend `validateGraph`
(`frontend/lib/agent-graph.ts`) is UX feedback only — direct API writes can
bypass it — so the rule set here MUST stay in parity with the frontend.

It carries two rules beyond the frontend's structural set:
- graph + realtime mode is a blocking error (graph node execution needs
  mid-session instruction swaps the Gemini Live realtime backend rejects/ignores)
- a `tool_result` edge with a non-empty `condition` is a warning (v1 treats all
  tool_result transitions as unconditional; see graph-execution spec)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

GRAPH_NODE_TYPES: tuple[str, ...] = ("start", "prompt", "end", "handoff")
EDGE_TRIGGERS: tuple[str, ...] = ("user_turn", "tool_result")
# cleanLegacyTools strips these from config.tools, so the legal-tool check must
# include them explicitly or the handoff flow itself would be flagged dangling.
AUTO_MOUNTED_TOOL_NAMES: tuple[str, ...] = ("lookup_qa", "transfer_to_human")


@dataclass
class GraphIssue:
    code: str
    message: str


@dataclass
class GraphValidation:
    errors: list[GraphIssue] = field(default_factory=list)
    warnings: list[GraphIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0


def edge_trigger(edge: dict) -> str:
    return "tool_result" if edge.get("trigger") == "tool_result" else "user_turn"


# ── normalize_graph (load-boundary sanitizer) ──────────────────────
# config_json is free-form: hand-edited YAML or direct API writes can produce a
# graph block missing any field. Everything downstream (validator, executor)
# assumes the full shape, so the load boundary coerces it here. Returns None for
# anything unusable (no/empty nodes), mirroring the frontend `normalizeGraph`.
def normalize_graph(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list):
        return None

    def _str(v: object, fallback: str = "") -> str:
        return v if isinstance(v, str) else fallback

    def _num(v: object) -> float:
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0

    nodes: list[dict] = []
    for i, n in enumerate(raw_nodes):
        if not isinstance(n, dict):
            continue
        pos = n.get("position") if isinstance(n.get("position"), dict) else {}
        raw_tools = n.get("tools")
        nodes.append(
            {
                "id": _str(n.get("id"), f"node-{i}"),
                # Unknown types survive so validate_graph can flag them.
                "type": _str(n.get("type"), "prompt"),
                "title": _str(n.get("title")),
                "prompt": _str(n.get("prompt")),
                "tools": [t for t in raw_tools if isinstance(t, str)] if isinstance(raw_tools, list) else [],
                "position": {"x": _num(pos.get("x")), "y": _num(pos.get("y"))},
            }
        )
    if not nodes:
        return None

    raw_edges = raw.get("edges") if isinstance(raw.get("edges"), list) else []
    edges: list[dict] = []
    for i, e in enumerate(raw_edges):
        if not isinstance(e, dict):
            continue
        edge: dict = {
            "id": _str(e.get("id"), f"edge-{i}"),
            "source": _str(e.get("source")),
            "target": _str(e.get("target")),
            "condition": _str(e.get("condition")),
        }
        if isinstance(e.get("trigger"), str):
            edge["trigger"] = e["trigger"]
        if isinstance(e.get("label"), str) and e["label"]:
            edge["label"] = e["label"]
        edges.append(edge)

    sv = raw.get("schema_version")
    return {
        "schema_version": sv if isinstance(sv, int) and not isinstance(sv, bool) else 1,
        "global_prompt": _str(raw.get("global_prompt")),
        "nodes": nodes,
        "edges": edges,
    }


# ── validate_graph (runtime gate + save-time hard validation truth) ──
def validate_graph(
    graph: dict,
    available_tools: list[str],
    config_tool_names: list[str] | None = None,
    *,
    handoff_enabled: bool = False,
    mode: str | None = None,
) -> GraphValidation:
    """Structural validation in parity with the frontend `validateGraph`, plus
    the graph+realtime mode conflict and tool_result-condition rules.

    `mode` is the profile's effective agent mode (`pipeline` / `realtime`); when
    `realtime`, the graph+realtime combination is a blocking error.
    """
    config_tool_names = config_tool_names or []
    result = GraphValidation()
    nodes: list[dict] = graph.get("nodes", [])
    edges: list[dict] = graph.get("edges", [])

    # ── graph + realtime mode conflict (mode coupling) ──
    if mode is not None and str(mode).strip().lower() == "realtime":
        result.errors.append(
            GraphIssue(
                "graph_realtime_conflict",
                "graph 執行僅支援 pipeline mode——graph 與 realtime 互斥（realtime 下 node "
                "切換的 instruction 更新會被 Gemini Live 1007 拒絕或靜默忽略）",
            )
        )

    # ── node ids + types ──
    seen_ids: set[str] = set()
    for node in nodes:
        nid = node.get("id", "")
        if nid in seen_ids:
            result.errors.append(GraphIssue("duplicate_node_id", f"節點 id 重複：{nid}"))
        seen_ids.add(nid)
        if node.get("type") not in GRAPH_NODE_TYPES:
            label = node.get("title") or nid
            result.errors.append(
                GraphIssue("invalid_node_type", f"節點「{label}」的 type 非法：{node.get('type')}")
            )

    # ── edge ids + self-loops ──
    seen_edge_ids: set[str] = set()
    for edge in edges:
        eid = edge.get("id", "")
        if eid in seen_edge_ids:
            result.errors.append(GraphIssue("duplicate_edge_id", f"邊 id 重複：{eid}"))
        seen_edge_ids.add(eid)
        if edge.get("source") and edge.get("source") == edge.get("target"):
            result.warnings.append(
                GraphIssue("self_loop", f"邊 {eid} 的起點與終點是同一節點（自我迴圈）")
            )

    # ── handoff node but handoff disabled ──
    if not handoff_enabled and any(n.get("type") == "handoff" for n in nodes):
        result.warnings.append(
            GraphIssue(
                "handoff_disabled",
                "graph 含轉真人節點，但 Handoff（human_operator）未啟用——執行時無 "
                "transfer_to_human 工具可呼叫",
            )
        )

    # ── exactly one start ──
    start_nodes = [n for n in nodes if n.get("type") == "start"]
    if len(start_nodes) == 0:
        result.errors.append(GraphIssue("no_start", "缺少 start 入口節點"))
    elif len(start_nodes) > 1:
        result.errors.append(GraphIssue("multiple_start", "start 入口節點只能有一個"))

    node_by_id = {n.get("id"): n for n in nodes}

    # ── edge endpoints, direction rules, trigger validity ──
    for edge in edges:
        eid = edge.get("id", "")
        for endpoint in (edge.get("source"), edge.get("target")):
            if endpoint not in node_by_id:
                result.errors.append(
                    GraphIssue("edge_endpoint_missing", f"邊 {eid} 引用不存在的節點：{endpoint}")
                )
        target = node_by_id.get(edge.get("target"))
        if target and target.get("type") == "start":
            result.errors.append(GraphIssue("edge_into_start", f"start 節點不可有入邊（{eid}）"))
        source = node_by_id.get(edge.get("source"))
        if source and source.get("type") == "end":
            result.errors.append(GraphIssue("edge_out_of_end", f"end 節點不可有出邊（{eid}）"))
        trigger = edge.get("trigger")
        if trigger is not None and trigger not in EDGE_TRIGGERS:
            result.errors.append(GraphIssue("invalid_trigger", f"邊 {eid} 的 trigger 非法：{trigger}"))
        # v1 不支援 tool_result 邊的非空 condition（當無條件處理，validator 標示）
        if edge_trigger(edge) == "tool_result" and (edge.get("condition") or "").strip():
            result.warnings.append(
                GraphIssue(
                    "tool_result_condition",
                    f"邊 {eid} 為 tool_result 且帶 condition——v1 不支援條件式 tool_result，"
                    f"執行時一律當無條件轉移",
                )
            )

    # ── reachability from start (BFS) ──
    if len(start_nodes) == 1:
        reached = {start_nodes[0].get("id")}
        queue = deque([start_nodes[0].get("id")])
        while queue:
            current = queue.popleft()
            for edge in edges:
                tgt = edge.get("target")
                if edge.get("source") == current and tgt in node_by_id and tgt not in reached:
                    reached.add(tgt)
                    queue.append(tgt)
        for node in nodes:
            if node.get("id") not in reached:
                label = node.get("title") or node.get("id")
                result.errors.append(GraphIssue("unreachable_node", f"節點「{label}」從 start 不可達"))

    # ── multiple unconditional out-edges on one (source, trigger) ──
    unconditional_seen: set[str] = set()
    for edge in edges:
        if (edge.get("condition") or "").strip():
            continue
        key = f"{edge.get('source')}::{edge_trigger(edge)}"
        if key in unconditional_seen:
            label = (node_by_id.get(edge.get("source")) or {}).get("title") or edge.get("source")
            result.warnings.append(
                GraphIssue(
                    "ambiguous_unconditional",
                    f"節點「{label}」有多條無條件出邊，依順序優先，後面的永遠不會生效",
                )
            )
        unconditional_seen.add(key)

    # ── tool_result edge from a node with no domain tool → dead transition ──
    # The runtime wraps a node's domain tools to hand off after they return; a
    # node sourcing a tool_result edge but listing no domain tool (empty, or only
    # auto-mounted) has nothing to wrap, so that transition can never fire.
    toolresult_sources = {e.get("source") for e in edges if edge_trigger(e) == "tool_result"}
    for node in nodes:
        if node.get("id") in toolresult_sources:
            domain_tools = [t for t in node.get("tools", []) if t not in AUTO_MOUNTED_TOOL_NAMES]
            if not domain_tools:
                label = node.get("title") or node.get("id")
                result.warnings.append(
                    GraphIssue(
                        "tool_result_no_tool",
                        f"節點「{label}」有 tool_result 出邊但沒有 domain 工具——該轉移永遠不會觸發",
                    )
                )

    # ── dangling tool references ──
    # Skip when builtin list failed to load (empty) to avoid false warnings.
    if available_tools:
        legal = {*config_tool_names, *available_tools, *AUTO_MOUNTED_TOOL_NAMES}
        for node in nodes:
            for tool in node.get("tools", []):
                if tool not in legal:
                    label = node.get("title") or node.get("id")
                    result.warnings.append(
                        GraphIssue("dangling_tool", f"節點「{label}」引用了不存在的工具：{tool}")
                    )

    return result


def _handoff_enabled(config: dict) -> bool:
    """Mirror of agent_factory._human_operator_enabled (kept inline so this module
    stays free of agent_factory/agent_tools imports). Backward-compat: new
    namespace `human_operator.enabled` or legacy `human_operator_instructions`."""
    ho = config.get("human_operator")
    if isinstance(ho, dict):
        return bool(ho.get("enabled", False))
    return bool(config.get("human_operator_instructions"))


def validate_profile_config(
    config: dict, available_tools: list[str], *, mode: str | None = None
) -> GraphValidation | None:
    """Orchestration shared by the API save gate and the runtime execution gate.

    Returns None (passthrough) when the profile is NOT in graph mode, or is in
    graph mode but has no usable `graph` block — both fall back to `instructions`
    rather than failing (mirrors the frontend `prepareGraphSave` passthrough and
    the graph-agent-schema fallback boundary). Otherwise returns the structural
    validation; callers reject the save (422) or fall back at runtime when invalid.

    `mode` is the profile's declared `models.mode`; only an explicit `realtime`
    triggers the graph+realtime conflict (unset is handled by the runtime gate).
    """
    if config.get("editor_mode") != "graph":
        return None
    graph = normalize_graph(config.get("graph"))
    if graph is None:
        return None
    config_tool_names = [
        t.get("name") for t in config.get("tools", []) if isinstance(t, dict) and t.get("name")
    ]
    return validate_graph(
        graph,
        available_tools,
        config_tool_names,
        handoff_enabled=_handoff_enabled(config),
        mode=mode,
    )
