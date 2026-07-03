"""LLM-backed profile text test runner (kind: llm_text).

Runs a real LLM conversation against a saved profile without a LiveKit room,
STT, TTS, or external tool side effects. Prompt-mode profiles get the same
system instructions the runtime agent uses; graph-mode profiles get a graph
text runner whose node routing is decided by real LLM tool calls (synthetic
``goto_*`` transition tools mirroring the runtime handoff tools).

Verified against livekit-agents 1.5.2 (task 2.0 spike):
- ``llm.chat(chat_ctx=..., tools=[...])`` streams ``ChatChunk``s whose
  ``delta.tool_calls`` carry ``FunctionToolCall(name, arguments, call_id)``.
- Tool results feed back as ``FunctionCall`` + ``FunctionCallOutput`` items.
- Final chunks may carry ``usage`` (CompletionUsage).
- No room/job context is needed; only an http session context for the
  inference gateway paths.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session as DbSession

from agent_tools import get_available_tools
from agent_factory import (
    _build_node_instructions,
    _compose_global_preamble,
    _transition_tool_name,
    compose_prompt_instructions,
)
from db.models import Profile, ProfileTestRun
from db import test_run_store
from db.event_sanitizer import sanitize_llm_text
from runtime.graph import edge_trigger, normalize_graph, validate_profile_config
from runtime.profile_test_runner import ToolDispatcher, _declared_tools, _profile_config, _tool_def_by_name
from runtime.providers import resolve_text_test_llm

TURN_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_STEPS = 10


@dataclass(frozen=True)
class LLMTextTestRequest:
    messages: list[str]
    tool_execution_mode: str = "dry_run"
    max_steps: int = DEFAULT_MAX_STEPS


@dataclass
class _UsageTotals:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def add(self, usage: Any) -> None:
        if usage is None:
            return
        self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
        self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
        self.total_tokens += getattr(usage, "total_tokens", 0) or 0
        self.calls += 1

    def as_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.calls,
        }


def run_profile_llm_text_test(
    db: DbSession,
    *,
    profile: Profile,
    request: LLMTextTestRequest,
    llm_component: Any | None = None,
) -> ProfileTestRun:
    """Run an LLM-backed text test and persist structured events.

    ``llm_component`` overrides the resolved LLM (tests inject a fake here);
    when None the profile's LLM spec is resolved via ``resolve_text_test_llm``.
    """
    started = time.perf_counter()
    messages = [m for m in (request.messages or []) if str(m).strip()]
    run = test_run_store.create_run(
        db,
        profile=profile,
        user_message=messages[0] if messages else "",
        user_messages=messages,
        tool_execution_mode=request.tool_execution_mode,
        status="running",
        kind="llm_text",
    )
    dispatcher = ToolDispatcher(request.tool_execution_mode)
    usage = _UsageTotals()

    try:
        if not messages:
            raise ValueError("llm_text run requires at least one non-empty message")
        config = _profile_config(profile)
        mode = ((config.get("models") or {}).get("mode") or "pipeline").strip().lower()

        test_run_store.append_event(
            db,
            run.id,
            event_type="test_started",
            payload={
                "kind": "llm_text",
                "profile_id": profile.id,
                "profile_name": profile.name,
                "profile_config_hash": run.profile_config_hash,
                "tool_execution_mode": request.tool_execution_mode,
                "messages": messages,
                "caveat": (
                    "LLM text tests call a real LLM (token cost applies) but do not "
                    "start a LiveKit room, use voice, or execute external tool side effects."
                ),
            },
        )

        llm_comp = llm_component
        fallback_reason = "realtime_text_fallback" if mode == "realtime" else None
        if llm_comp is None:
            llm_comp, _used, fallback_reason = resolve_text_test_llm(config)
        if fallback_reason:
            test_run_store.append_event(
                db,
                run.id,
                event_type="llm_fallback",
                severity="warning",
                payload={
                    "reason": fallback_reason,
                    "message": "以 fallback LLM 執行文字測試，非 realtime 模型；回覆行為可能與生產環境不同。",
                },
            )

        graph_validation = validate_profile_config(config, get_available_tools(), mode=mode)
        use_graph = (
            config.get("editor_mode") == "graph"
            and graph_validation is not None
            and graph_validation.valid
            and mode == "pipeline"
        )

        if use_graph:
            summary_extra = asyncio.run(
                _run_graph_text(db, run, config, messages, dispatcher, llm_comp, usage, request.max_steps)
            )
        else:
            if config.get("editor_mode") == "graph":
                reason = "graph_realtime_fallback" if mode != "pipeline" else (
                    "graph_missing_or_unusable" if graph_validation is None else "graph_validation_failed"
                )
                test_run_store.append_event(
                    db,
                    run.id,
                    event_type="fallback",
                    severity="warning",
                    payload={"reason": reason},
                )
            summary_extra = asyncio.run(
                _run_prompt_text(db, run, config, messages, dispatcher, llm_comp, usage, request.max_steps)
            )

        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        test_run_store.append_event(
            db,
            run.id,
            event_type="test_completed",
            payload={
                "status": "completed",
                "kind": "llm_text",
                "tool_execution_mode": request.tool_execution_mode,
                "elapsed_ms": elapsed_ms,
                "usage": usage.as_dict(),
            },
        )
        return test_run_store.finalize_run(
            db,
            run.id,
            status="completed",
            final_summary={
                "status": "completed",
                "kind": "llm_text",
                "tool_execution_mode": request.tool_execution_mode,
                "turns": len(messages),
                "usage": usage.as_dict(),
                "llm_fallback": fallback_reason,
                **summary_extra,
            },
        ) or run
    except Exception as exc:
        test_run_store.append_event(
            db,
            run.id,
            event_type="runner_error",
            severity="error",
            payload={"error_type": type(exc).__name__, "message": str(exc)},
        )
        test_run_store.append_event(
            db,
            run.id,
            event_type="test_completed",
            severity="error",
            payload={
                "status": "failed",
                "kind": "llm_text",
                "error_type": type(exc).__name__,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "usage": usage.as_dict(),
            },
        )
        return test_run_store.finalize_run(
            db,
            run.id,
            status="failed",
            final_summary={
                "status": "failed",
                "kind": "llm_text",
                "error_type": type(exc).__name__,
                "usage": usage.as_dict(),
            },
        ) or run


# ── Chat plumbing ──────────────────────────────────────────


def _ensure_http_context() -> None:
    """Inference gateway components need an http session context; a bare
    asyncio loop (no LiveKit job) doesn't have one."""
    from livekit.agents.utils import http_context

    try:
        http_context.http_session()
    except RuntimeError:
        http_context._new_session_ctx()


async def _chat_once(
    llm_comp: Any,
    *,
    instructions: str,
    history: list[Any],
    tools: list[Any],
) -> tuple[str, list[Any], Any]:
    """One LLM call: returns (text, tool_calls, usage)."""
    from livekit.agents.llm import ChatContext

    ctx = ChatContext.empty()
    if instructions:
        ctx.add_message(role="system", content=instructions)
    for item in history:
        ctx.insert(item)

    text_parts: list[str] = []
    tool_calls: list[Any] = []
    usage = None
    async with asyncio.timeout(TURN_TIMEOUT_SECONDS):
        stream = llm_comp.chat(chat_ctx=ctx, tools=tools or None)
        async with stream:
            async for chunk in stream:
                delta = getattr(chunk, "delta", None)
                if delta is not None:
                    if delta.content:
                        text_parts.append(delta.content)
                    if delta.tool_calls:
                        tool_calls.extend(delta.tool_calls)
                if getattr(chunk, "usage", None) is not None:
                    usage = chunk.usage
    return "".join(text_parts), tool_calls, usage


def _history_user(history: list[Any], text: str) -> None:
    from livekit.agents.llm import ChatContext

    scratch = ChatContext.empty()
    scratch.add_message(role="user", content=text)
    history.extend(scratch.items)


def _history_assistant(history: list[Any], text: str) -> None:
    from livekit.agents.llm import ChatContext

    scratch = ChatContext.empty()
    scratch.add_message(role="assistant", content=text)
    history.extend(scratch.items)


def _history_tool_exchange(history: list[Any], call: Any, output: dict[str, Any]) -> None:
    from livekit.agents.llm import FunctionCall, FunctionCallOutput

    call_id = getattr(call, "call_id", None) or f"call_{uuid.uuid4().hex[:8]}"
    history.append(
        FunctionCall(call_id=call_id, name=call.name, arguments=call.arguments or "{}")
    )
    history.append(
        FunctionCallOutput(
            call_id=call_id,
            name=call.name,
            output=json.dumps(output, ensure_ascii=False, default=str),
            is_error=False,
        )
    )


def _make_schema_tool(name: str, description: str, parameters: dict[str, Any] | None) -> Any:
    """Advertise-only tool: schema goes to the LLM; the function body never runs
    because the runner intercepts tool calls from the stream itself."""
    from livekit.agents.llm import function_tool

    async def _noop() -> None:  # pragma: no cover - never invoked
        return None

    schema = parameters if isinstance(parameters, dict) and parameters.get("type") else {
        "type": "object",
        "properties": {},
    }
    return function_tool(
        _noop,
        raw_schema={"name": name, "description": description or name, "parameters": schema},
    )


def _domain_tools_for(config: dict[str, Any], tool_names: list[str] | None = None) -> list[Any]:
    tools = []
    declared = _declared_tools(config)
    if tool_names is not None:
        declared = [t for t in declared if t.get("name") in set(tool_names)]
    for tool_def in declared:
        tools.append(
            _make_schema_tool(
                tool_def["name"],
                str(tool_def.get("description") or ""),
                tool_def.get("parameters"),
            )
        )
    return tools


def _record_llm_response(db: DbSession, run_id: str, *, turn: int, text: str, node_id: str | None = None) -> None:
    payload: dict[str, Any] = {"turn": turn, "text": sanitize_llm_text(text)}
    if node_id is not None:
        payload["node_id"] = node_id
    test_run_store.append_event(db, run_id, event_type="llm_response", payload=payload)


def _record_usage(db: DbSession, run_id: str, usage: Any, totals: _UsageTotals) -> None:
    if usage is None:
        return
    totals.add(usage)
    test_run_store.append_event(
        db,
        run_id,
        event_type="token_usage",
        payload={
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
        },
    )


def _dispatch_domain_tool(
    db: DbSession,
    run_id: str,
    dispatcher: ToolDispatcher,
    config: dict[str, Any],
    call: Any,
) -> dict[str, Any]:
    tool_def = _tool_def_by_name(config, call.name)
    result = dispatcher.dispatch(call.name, tool_def)
    test_run_store.append_event(
        db,
        run_id,
        event_type="tool_call",
        payload={**result, "arguments": _parse_arguments(call)},
    )
    test_run_store.append_event(
        db,
        run_id,
        event_type="tool_result",
        payload={"tool_name": call.name, "result": result.get("result")},
    )
    return result.get("result") or {}


def _parse_arguments(call: Any) -> Any:
    try:
        return json.loads(call.arguments) if call.arguments else {}
    except (json.JSONDecodeError, TypeError):
        return {"raw": str(call.arguments)}


# ── Prompt mode ────────────────────────────────────────────


async def _run_prompt_text(
    db: DbSession,
    run: ProfileTestRun,
    config: dict[str, Any],
    messages: list[str],
    dispatcher: ToolDispatcher,
    llm_comp: Any,
    usage: _UsageTotals,
    max_steps: int,
) -> dict[str, Any]:
    _ensure_http_context()
    instructions = compose_prompt_instructions(config)
    test_run_store.append_event(
        db,
        run.id,
        event_type="prompt_rendered",
        payload={"mode": "prompt", "instruction_chars": len(instructions)},
    )

    tools = _domain_tools_for(config)
    history: list[Any] = []
    last_response = ""

    for turn, message in enumerate(messages, start=1):
        _history_user(history, message)
        steps = 0
        while True:
            steps += 1
            if steps > max_steps:
                test_run_store.append_event(
                    db,
                    run.id,
                    event_type="max_steps_reached",
                    severity="warning",
                    payload={"turn": turn, "max_steps": max_steps},
                )
                break
            text, tool_calls, chunk_usage = await _chat_once(
                llm_comp, instructions=instructions, history=history, tools=tools
            )
            _record_usage(db, run.id, chunk_usage, usage)
            if tool_calls:
                if text:
                    _history_assistant(history, text)
                for call in tool_calls:
                    result = _dispatch_domain_tool(db, run.id, dispatcher, config, call)
                    _history_tool_exchange(history, call, result)
                continue
            last_response = text
            _history_assistant(history, text)
            _record_llm_response(db, run.id, turn=turn, text=text)
            break

    return {"assistant_output": sanitize_llm_text(last_response)}


# ── Graph mode ─────────────────────────────────────────────


async def _run_graph_text(
    db: DbSession,
    run: ProfileTestRun,
    config: dict[str, Any],
    messages: list[str],
    dispatcher: ToolDispatcher,
    llm_comp: Any,
    usage: _UsageTotals,
    max_steps: int,
) -> dict[str, Any]:
    _ensure_http_context()
    graph = normalize_graph(config.get("graph")) or {"nodes": [], "edges": []}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_by_id = {node.get("id"): node for node in nodes}
    preamble = _compose_global_preamble(config, graph)

    current = next(node for node in nodes if node.get("type") == "start")
    graph_path: list[str] = []
    termination_reason = "messages_exhausted"
    last_response = ""

    def _user_edges(node_id: str) -> list[dict[str, Any]]:
        return [e for e in edges if e.get("source") == node_id and edge_trigger(e) == "user_turn"]

    def _tool_result_edge(node_id: str) -> dict[str, Any] | None:
        for e in edges:
            if e.get("source") == node_id and edge_trigger(e) == "tool_result":
                return e
        return None

    def _node_tools(node: dict[str, Any]) -> tuple[list[Any], dict[str, str]]:
        """(advertised tools, goto tool name -> target node id)."""
        tools = _domain_tools_for(config, node.get("tools") or [])
        goto_targets: dict[str, str] = {}
        for e in _user_edges(node.get("id")):
            target = e.get("target")
            if not target:
                continue
            name = _transition_tool_name(target)
            cond = (e.get("condition") or "").strip()
            desc = (
                f"當以下情況成立時呼叫，進入下一對話階段：{cond}"
                if cond
                else "準備好進入下一對話階段時呼叫（無條件轉移）。"
            )
            tools.append(_make_schema_tool(name, desc, None))
            goto_targets[name] = target
        return tools, goto_targets

    def _enter(node: dict[str, Any]) -> None:
        graph_path.append(str(node.get("id")))
        test_run_store.append_event(
            db,
            run.id,
            event_type="node_entered",
            payload={
                "node_id": node.get("id"),
                "node_type": node.get("type"),
                "title": node.get("title") or node.get("id"),
            },
        )

    def _emit_edge(edge_like: dict[str, Any], trigger: str) -> None:
        test_run_store.append_event(
            db,
            run.id,
            event_type="edge_selected",
            payload={
                "source": edge_like.get("source"),
                "target": edge_like.get("target"),
                "trigger": trigger,
                "condition": edge_like.get("condition") or "",
            },
        )

    test_run_store.append_event(
        db,
        run.id,
        event_type="graph_validated",
        payload={"node_count": len(nodes), "edge_count": len(edges)},
    )
    _enter(current)

    history: list[Any] = []
    total_steps = 0
    terminated = False

    for turn, message in enumerate(messages, start=1):
        if terminated:
            break
        _history_user(history, message)
        while True:
            total_steps += 1
            if total_steps > max_steps:
                test_run_store.append_event(
                    db,
                    run.id,
                    event_type="max_steps_reached",
                    severity="warning",
                    payload={"turn": turn, "max_steps": max_steps},
                )
                termination_reason = "max_steps"
                terminated = True
                break

            instructions = _build_node_instructions(preamble, current, _user_edges(current.get("id")))
            tools, goto_targets = _node_tools(current)
            text, tool_calls, chunk_usage = await _chat_once(
                llm_comp, instructions=instructions, history=history, tools=tools
            )
            _record_usage(db, run.id, chunk_usage, usage)

            if tool_calls:
                if text:
                    _history_assistant(history, text)
                transitioned = False
                for call in tool_calls:
                    if call.name in goto_targets:
                        target_id = goto_targets[call.name]
                        _history_tool_exchange(history, call, {"transitioned": True, "target": target_id})
                        _emit_edge(
                            {"source": current.get("id"), "target": target_id},
                            "user_turn",
                        )
                        current = node_by_id.get(target_id) or current
                        _enter(current)
                        transitioned = True
                    else:
                        result = _dispatch_domain_tool(db, run.id, dispatcher, config, call)
                        _history_tool_exchange(history, call, result)
                        tr_edge = _tool_result_edge(current.get("id"))
                        if tr_edge and tr_edge.get("target") in node_by_id:
                            # Runtime parity: tool_result edges transition
                            # unconditionally; the TARGET node speaks with the
                            # tool result already in context.
                            _emit_edge(tr_edge, "tool_result")
                            current = node_by_id[tr_edge.get("target")]
                            _enter(current)
                            transitioned = True

                if current.get("type") == "handoff":
                    test_run_store.append_event(
                        db,
                        run.id,
                        event_type="handoff",
                        payload={
                            "target_node_id": current.get("id"),
                            "target_title": current.get("title"),
                        },
                    )
                    termination_reason = "handoff"
                    terminated = True
                    break
                if current.get("type") == "end":
                    termination_reason = "end_node"
                    terminated = True
                    break
                # Let the (possibly new) node produce its reply.
                _ = transitioned
                continue

            last_response = text
            _history_assistant(history, text)
            _record_llm_response(db, run.id, turn=turn, text=text, node_id=str(current.get("id")))
            break

    return {
        "assistant_output": sanitize_llm_text(last_response),
        "graph_path": graph_path,
        "termination_reason": termination_reason,
    }
