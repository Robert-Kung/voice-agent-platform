"""
Agent Factory — 從 DB 或 YAML profile 動態建立 LiveKit Voice Agent

用法：
    profile = load_profile("car_inspection")       # 先查 DB，fallback 到 YAML
    PhoneAgent = create_agent_class(profile)

工具掛載規則（見 CLAUDE.md 的三層架構）：
- Tier 1（get_current_time）：YAML tools 區塊宣告才掛
- Tier 2 自動掛載：
    lookup_qa：profile.qa_mode == "tool" 且 qa_data 存在 → 自動掛
    transfer_to_human：profile.human_operator.enabled == true → 自動掛
  否則資料嵌入 instructions（lookup_qa inline mode、services hours）
- Tier 3（HTTP tool）：YAML tools 區塊宣告（待實作）
"""

import functools
import json
import logging
import pathlib
import re

import yaml

from livekit.agents import Agent, StopResponse, function_tool
from agent_tools import TOOL_REGISTRY, build_tools_for_agent, get_available_tools
from runtime.graph import edge_trigger, normalize_graph, validate_graph

logger = logging.getLogger("agent-factory")

PROFILES_DIR = pathlib.Path(__file__).parent / "profiles"

# Default 為 inline — QA 在 session 開始時一次嵌入 instructions，零延遲。
# 切到 "tool" 適合 QA 量大會撐爆 context 的場域。
_DEFAULT_QA_MODE = "inline"


# ── Render helpers (Tier 2 data → instructions) ────────────


def _render_qa_block(qa_data: list[dict]) -> str:
    """把 qa_data 渲染成 instructions 附加段落。"""
    if not qa_data:
        return ""
    lines = ["\n\n[常見問題知識庫] 以下問題直接用於回答，不需呼叫任何工具："]
    for item in qa_data:
        kw = "、".join(item.get("keywords", [])[:3])
        lines.append(f"▸ 關鍵字：{kw}")
        lines.append(f"  回答：{item.get('answer', '')}")
    return "\n".join(lines)


def _render_services_block(services: dict) -> str:
    """把 services 營業時間渲染成 instructions 附加段落。

    LLM 配合 get_current_time tool 自行判斷 is_open / closes_at，
    取代過去 check_business_status tool 的 runtime 計算。
    """
    if not services:
        return ""
    lines = ["\n\n[營業時間] 呼叫 get_current_time 取得當下時間後，依下列規則判斷服務是否營業："]
    for svc_name, svc in services.items():
        if svc.get("always_open"):
            lines.append(f"▸ {svc_name}：24 小時全天營業")
            continue
        hours_text = svc.get("hours_text", "")
        if isinstance(hours_text, dict):
            for slot_name, text in hours_text.items():
                lines.append(f"▸ {svc_name}（{slot_name}）：{text}")
        elif hours_text:
            lines.append(f"▸ {svc_name}：{hours_text}")
    return "\n".join(lines)


def _human_operator_enabled(profile: dict) -> bool:
    """支援新 namespace 與舊散落欄位的 backward-compat 檢查。"""
    ho = profile.get("human_operator")
    if isinstance(ho, dict):
        return bool(ho.get("enabled", False))
    # 舊 schema：只要有 human_operator_instructions 就視為啟用
    return bool(profile.get("human_operator_instructions"))


def _qa_mode(profile: dict) -> str:
    mode = profile.get("qa_mode", _DEFAULT_QA_MODE)
    if mode not in ("inline", "tool"):
        logger.warning("invalid qa_mode '%s', falling back to '%s'", mode, _DEFAULT_QA_MODE)
        return _DEFAULT_QA_MODE
    return mode


# ── Profile loading ────────────────────────────────────────


def list_profiles() -> list[str]:
    """列出所有可用的 profile 名稱（DB + YAML 合併去重）。"""
    yaml_names = sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))

    try:
        from db.engine import get_session_factory
        from db.profile_store import list_profiles as db_list_profiles
        factory = get_session_factory()
        with factory() as db:
            db_profiles = db_list_profiles(db)
            db_names = [p.name for p in db_profiles]
        all_names = sorted(set(yaml_names + db_names))
        return all_names
    except Exception:
        logger.exception("DB unavailable while listing profiles; falling back to YAML only")
        return yaml_names


def load_profile_with_id(name: str) -> tuple[dict, str | None]:
    """讀取 profile 並同時回傳 DB profile id。

    先查 DB（active profile），找不到 fallback 到 YAML。

    Returns:
        (config_dict, db_profile_id)
        db_profile_id 為 None 代表從 YAML 載入，無 DB 記錄可連結。

    不把 db_profile_id 塞進 config dict — 避免 admin UI 把 config 存回
    DB 時順便把 _db_profile_id 持久化，造成 config 每輪都膨脹。
    """
    # 1. 嘗試 DB
    try:
        from db.engine import get_session_factory
        from db.profile_store import get_profile_by_name
        factory = get_session_factory()
        with factory() as db:
            profile = get_profile_by_name(db, name)
            if profile is not None:
                if not profile.is_active:
                    raise ValueError(
                        f"Profile '{name}' is deactivated. "
                        f"Re-activate it via the admin API before use."
                    )
                data = json.loads(profile.config_json)
                logger.info("Loaded profile '%s' from DB (id=%s)", name, profile.id)
                return (data, profile.id)
    except ValueError:
        raise  # Let deactivation errors propagate — do NOT fallback to YAML
    except Exception:
        logger.exception("DB profile load failed for '%s'; falling back to YAML", name)

    # 2. Fallback: YAML
    path = PROFILES_DIR / f"{name}.yaml"
    if not path.exists():
        available = list_profiles()
        raise FileNotFoundError(
            f"Profile '{name}' not found.\n"
            f"Available profiles: {', '.join(available)}\n"
            f"Profiles directory: {PROFILES_DIR}"
        )
    with open(path, "r", encoding="utf-8") as f:
        return (yaml.safe_load(f), None)


def load_profile(name: str) -> dict:
    """讀取 profile（僅 config，丟棄 DB id）— 相容舊呼叫端。"""
    config, _ = load_profile_with_id(name)
    return config


# ── Dynamic Agent class creation ───────────────────────────


def create_agent_class(profile: dict, mode: str = "pipeline"):
    """
    根據 profile 動態建立主要 Phone Agent class。

    tools 來源：
    1. 若 profile 有 tools 區塊 → 只建立宣告的 tools（附帶各自 config）
    2. 若 profile 沒有 tools 區塊 → 不附加任何 tool（純對話 agent）

    每個 tool 由 agent_tools.py 的 TOOL_REGISTRY 工廠函式建立。

    mode：
      - "pipeline"：session.say() 逐字播放歡迎詞（需要獨立 TTS）
      - "realtime"：session.generate_reply() 觸發 RealtimeModel 說出歡迎詞

    注意：generate_reply() 在 on_enter 呼叫時屬於第一個 model turn 之前，
    此時 send_client_content 對 Gemini 3.1 仍有效。
    mid-session（第一個 model turn 完成後）才會被 1007 拒絕。
    """
    agent_instructions = profile.get("instructions", "")
    welcome = profile.get("welcome_message", "您好，請問有什麼可以為您服務的？")
    # Realtime 用描述性指令（Gemini 自然生成），Pipeline 用逐字稿（TTS 直讀）
    welcome_instructions = profile.get(
        "welcome_instructions",
        "向來電者打招呼，簡短介紹自己並詢問需要什麼協助。"
    )

    # ── Tier 2 資料 → instructions ────────────────────────
    qa_mode = _qa_mode(profile)
    qa_data = profile.get("qa_data", [])
    if qa_mode == "inline" and qa_data:
        agent_instructions += _render_qa_block(qa_data)
        logger.info("QA inline mode: 嵌入 %d 筆 QA（總 %d chars）", len(qa_data), len(agent_instructions))

    services = profile.get("services", {})
    if services:
        agent_instructions += _render_services_block(services)
        logger.info("Services 嵌入 instructions: %d 個服務項目", len(services))

    # ── Tool 建立 ──────────────────────────────────────────
    # 1. profile.tools 宣告的 user-side tools（Tier 1 + 未來的 Tier 3 HTTP tools）
    tool_methods = build_tools_for_agent(profile)

    # 2. 自動掛載 Tier 2 條件性 tools
    if qa_mode == "tool" and qa_data and "lookup_qa" not in tool_methods:
        lookup_qa_factory = TOOL_REGISTRY["lookup_qa"]
        tool_methods["lookup_qa"] = lookup_qa_factory(profile, {})
        logger.info("QA tool mode: auto-mounted lookup_qa")

    if _human_operator_enabled(profile) and "transfer_to_human" not in tool_methods:
        ho_config = profile.get("human_operator", {}) if isinstance(profile.get("human_operator"), dict) else {}
        transfer_factory = TOOL_REGISTRY["transfer_to_human"]
        tool_methods["transfer_to_human"] = transfer_factory(profile, ho_config)
        logger.info("Human operator enabled: auto-mounted transfer_to_human")

    class DynamicPhoneAgent(Agent):
        def __init__(self) -> None:
            super().__init__(instructions=agent_instructions)

        async def on_enter(self) -> None:
            if mode == "realtime":
                # Realtime 模式：用描述性指令觸發 Gemini 自然生成歡迎語
                #
                # 不能放逐字稿！instructions 在 SDK 中會作為 user turn 送入模型，
                # 塞入完整歡迎文句 → Gemini 誤以為「使用者」在打招呼 → 回「聽不懂」。
                # 改用描述性指令（welcome_instructions），讓 Gemini 依角色自然開口。
                # welcome_message 保留給 pipeline 的 session.say() 使用。
                await self.session.generate_reply(
                    instructions=welcome_instructions,
                )
            else:
                # Pipeline 模式有獨立 TTS，直接播放逐字稿
                await self.session.say(welcome)

        async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
            """攔截 STT 文字，送入 Gemini RealtimeModel（僅 realtime 模式）。

            SDK 預設行為：對 RealtimeModel 會在 agent_activity.py:1839 將
            user_message 設為 None，導致 STT 轉錄文字被丟棄。
            generate_reply() 最終只送出 "." 佔位符，Gemini 只能依賴音頻上下文。

            此覆寫攔截 STT 文字 → session.generate_reply(user_input=text)
            → update_chat_ctx 送出實際文字 → generate_reply 觸發 Gemini 回覆。
            配合 TextInputRealtimeModel（push_audio=no-op），Gemini 完全基於
            文字上下文回覆，避免音頻 token 累積造成的延遲遞增。
            """
            if mode != "realtime":
                return  # pipeline 模式：交由 SDK 預設流程處理

            user_text = new_message.text_content
            if user_text:
                logger.info(
                    "Realtime text-input: forwarding STT text to Gemini (%d chars)",
                    len(user_text),
                )
                self.session.generate_reply(user_input=user_text)
            else:
                logger.warning("Realtime text-input: empty STT transcript, skipping reply")
            raise StopResponse()

    # 動態掛載 tool 方法到 class 上
    for tool_name, tool_method in tool_methods.items():
        setattr(DynamicPhoneAgent, tool_name, tool_method)

    profile_name = profile.get("name", "unknown")
    DynamicPhoneAgent.__name__ = f"PhoneAgent_{profile_name}"
    DynamicPhoneAgent.__qualname__ = DynamicPhoneAgent.__name__

    tool_names = list(tool_methods.keys()) if tool_methods else ["(none)"]
    logger.info(
        "Created agent '%s' with tools: %s",
        profile_name,
        ", ".join(tool_names),
    )

    return DynamicPhoneAgent


# ── Graph execution (graph-execution capability) ───────────
#
# graph-mode profiles assemble one Agent instance per node and wire edge
# transitions as SDK-native handoffs (a function tool returning the target Agent;
# generation.py:make_tool_output). v1 is pipeline-only — the runtime gate
# (build_root_agent) only reaches this path when editor_mode == 'graph', the
# backend validator passes, AND the effective mode is pipeline.


def _transition_tool_name(target_id: str) -> str:
    """Stable, schema-safe tool name for an edge into target_id."""
    return f"goto_{re.sub(r'[^0-9A-Za-z_]+', '_', target_id)}"


def _compose_global_preamble(profile: dict, graph: dict) -> str:
    """global_prompt + globally-injected QA/services, prepended to every node
    (graph-execution: global capabilities stay at the global level, not per node)."""
    parts: list[str] = []
    gp = (graph.get("global_prompt") or "").strip()
    if gp:
        parts.append(gp)
    qa_data = profile.get("qa_data", [])
    if _qa_mode(profile) == "inline" and qa_data:
        parts.append(_render_qa_block(qa_data).strip())
    services = profile.get("services", {})
    if services:
        parts.append(_render_services_block(services).strip())
    return "\n\n".join(p for p in parts if p)


def _build_node_instructions(preamble: str, node: dict, user_edges: list[dict]) -> str:
    """Compose a node Agent's instructions: global preamble + focused node prompt
    + explicit transition guidance for its user_turn edges."""
    parts: list[str] = []
    if preamble:
        parts.append(preamble)
    if (node.get("prompt") or "").strip():
        parts.append(node["prompt"].strip())
    if user_edges:
        lines = ["[轉移規則] 對話進行中，符合下列情況時呼叫對應工具進入下一階段（依序判斷，先命中者生效）："]
        for e in user_edges:
            cond = (e.get("condition") or "").strip()
            when = f"當「{cond}」" if cond else "準備好（無條件）時"
            lines.append(f"- {when} → 呼叫 {_transition_tool_name(e['target'])}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _make_transition_tool(registry: dict, target_id: str, condition: str):
    """A user_turn handoff tool: returning the target Agent triggers the SDK handoff.

    The target node sees the conversation so far because each node seeds the running
    session history on enter; whether to re-ask a given field is left to the node's
    own prompt, not enforced here."""
    cond = (condition or "").strip()
    desc = (
        f"當以下情況成立時呼叫，進入下一對話階段：{cond}"
        if cond
        else "準備好進入下一對話階段時呼叫（無條件轉移）。"
    )

    @function_tool(name=_transition_tool_name(target_id), description=desc)
    async def _goto(self):
        return registry[target_id]

    return _goto


def _wrap_domain_tool_for_handoff(tool, registry: dict, target_id: str):
    """Wrap a domain tool so it returns (result, target_agent): the LLM speaks the
    tool result, then the SDK hands off to the target (tool_result transition).
    functools.wraps preserves the original parameter schema via __wrapped__."""
    raw = tool._func

    @functools.wraps(raw)
    async def _wrapped(self, *args, **kwargs):
        result = await raw(self, *args, **kwargs)
        return (result, registry[target_id])

    return function_tool(_wrapped, name=tool.info.name, description=tool.info.description)


def _make_node_agent_class(node_instructions: str, node_type: str, welcome: str, tool_attrs: dict):
    """Build an Agent subclass for one node. start nodes greet with the welcome
    message; other nodes auto-continue on enter so a handoff doesn't leave the
    caller in silence waiting for the new node to speak."""

    class NodeAgent(Agent):
        def __init__(self) -> None:
            super().__init__(instructions=node_instructions)

        async def on_enter(self) -> None:
            if node_type == "start":
                await self.session.say(welcome)
                return
            # Each node Agent is built with an empty chat_ctx and the SDK does NOT
            # auto-seed it on handoff, so without this the node can't see anything the
            # caller already said and re-asks from scratch. Carry the running session
            # conversation in before generating.
            await self.update_chat_ctx(self.session.history)
            # A user_turn handoff returns only the target Agent (no reply_required), so
            # we kick the reply ourselves or the node stays silent until the caller speaks.
            self.session.generate_reply()

    for name, method in tool_attrs.items():
        setattr(NodeAgent, name, method)
    NodeAgent.__name__ = "NodeAgent"
    NodeAgent.__qualname__ = "NodeAgent"
    return NodeAgent


def build_graph_root_agent(profile: dict, mode: str, graph: dict) -> Agent:
    """Assemble a validated graph into wired Agent instances; return the start node's.

    Caller (build_root_agent) guarantees the graph passed structural validation and
    mode == 'pipeline'. Tools resolve through the profile's existing three-tier
    mounting; per-node model specs are an interface point (v1 inherits session model).
    """
    preamble = _compose_global_preamble(profile, graph)
    nodes = graph["nodes"]
    edges = graph["edges"]
    welcome = profile.get("welcome_message", "您好，請問有什麼可以為您服務的？")

    # Profile-declared domain tools, built once, selected per node by name.
    all_domain_tools = build_tools_for_agent(profile)
    qa_tool = None
    if _qa_mode(profile) == "tool" and profile.get("qa_data"):
        qa_tool = TOOL_REGISTRY["lookup_qa"](profile, {})
    handoff_tool = None
    if _human_operator_enabled(profile):
        ho_config = profile.get("human_operator", {}) if isinstance(profile.get("human_operator"), dict) else {}
        handoff_tool = TOOL_REGISTRY["transfer_to_human"](profile, ho_config)

    # Shared registry: transition tools resolve targets at call time, so forward
    # references across cycles are fine as long as it's fully populated before any call.
    registry: dict[str, Agent] = {}
    node_classes: dict[str, type] = {}

    for node in nodes:
        node_id = node["id"]
        out_edges = [e for e in edges if e["source"] == node_id]
        user_edges = [e for e in out_edges if edge_trigger(e) == "user_turn"]
        toolresult_edges = [e for e in out_edges if edge_trigger(e) == "tool_result"]

        tool_attrs: dict = {}
        # Node's declared domain tools (subset of profile tools by name).
        for tname in node.get("tools", []):
            if tname in all_domain_tools:
                tool_attrs[tname] = all_domain_tools[tname]
        # Auto-mounted lookup_qa on every node when in QA tool mode.
        if qa_tool is not None:
            tool_attrs["lookup_qa"] = qa_tool
        # handoff node: mount transfer_to_human; its prompt acts as the greeting.
        if node.get("type") == "handoff" and handoff_tool is not None:
            tool_attrs["transfer_to_human"] = handoff_tool

        # tool_result transitions: wrap this node's domain tools to hand off after
        # returning (v1 unconditional; first tool_result edge by array order wins).
        if toolresult_edges:
            target = toolresult_edges[0]["target"]
            for tname in list(tool_attrs.keys()):
                if tname in ("lookup_qa", "transfer_to_human"):
                    continue  # don't hijack global/handoff tools
                tool_attrs[tname] = _wrap_domain_tool_for_handoff(tool_attrs[tname], registry, target)

        # user_turn transitions.
        for e in user_edges:
            tool_attrs[_transition_tool_name(e["target"])] = _make_transition_tool(
                registry, e["target"], e.get("condition", "")
            )

        # Per-node model (multi-model OQ4): interface point only in v1.
        if node.get("model"):
            logger.info("Node '%s' declares a model spec (v1: using session-level model)", node_id)

        node_instructions = _build_node_instructions(preamble, node, user_edges)
        node_classes[node_id] = _make_node_agent_class(
            node_instructions, node.get("type", "prompt"), welcome, tool_attrs
        )

    for node_id, cls in node_classes.items():
        registry[node_id] = cls()

    start_id = next(n["id"] for n in nodes if n["type"] == "start")
    logger.info(
        "Graph assembled for '%s': %d nodes, %d edges, start=%s",
        profile.get("name", "?"), len(nodes), len(edges), start_id,
    )
    return registry[start_id]


def _select_graph_strategy(profile: dict, mode: str) -> tuple[bool, str]:
    """Runtime gate decision: (use_graph, reason). Never raises — a bad graph
    falls back to the flatten `instructions` (graph-execution: no fail-loud)."""
    if profile.get("editor_mode") != "graph":
        return False, "editor_mode != graph"
    if mode != "pipeline":
        return False, f"mode={mode}（graph 執行僅 pipeline）"
    graph = normalize_graph(profile.get("graph"))
    if graph is None:
        return False, "no usable graph block"
    config_tools = [t.get("name") for t in profile.get("tools", []) if isinstance(t, dict) and t.get("name")]
    # mode is always 'pipeline' here (the realtime early-return above guards it), so
    # the validator's graph_realtime_conflict rule only ever fires on the API save
    # path — at runtime, realtime is handled by the early-return, not this validator.
    result = validate_graph(
        graph, get_available_tools(), config_tools,
        handoff_enabled=_human_operator_enabled(profile), mode=mode,
    )
    if not result.valid:
        return False, "graph validation failed: " + ",".join(e.code for e in result.errors)
    return True, "ok"


def build_root_agent(profile: dict, mode: str = "pipeline") -> Agent:
    """Entry point for the session's root Agent (graph-execution strategy gate).

    Returns a graph's start-node Agent when the profile is graph-mode, valid, and
    pipeline; otherwise the single-instructions agent. Graph assembly failures fall
    back to instructions with a loud warning rather than dropping the call.
    """
    use_graph, reason = _select_graph_strategy(profile, mode)
    if use_graph:
        try:
            graph = normalize_graph(profile.get("graph"))
            return build_graph_root_agent(profile, mode, graph)
        except Exception:
            logger.exception("Graph assembly failed for '%s'; falling back to instructions",
                             profile.get("name", "?"))
            reason = "graph assembly raised"
    if profile.get("editor_mode") == "graph":
        logger.warning(
            "Graph-mode profile '%s' running flatten-instructions fallback: %s",
            profile.get("name", "?"), reason,
        )
    return create_agent_class(profile, mode)()
