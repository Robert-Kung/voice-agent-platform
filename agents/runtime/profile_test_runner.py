"""Synchronous profile flow test runner for admin-side smoke tests."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session as DbSession

from agent_tools import get_available_tools
from db.models import Profile, ProfileTestRun
from db import test_run_store
from runtime.graph import edge_trigger, normalize_graph, validate_profile_config

TEXT_RUN_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class TextTestRequest:
    message: str
    tool_execution_mode: str = "dry_run"


class ToolDispatcher:
    """Central test-run dispatcher for dry-run/live tool execution decisions."""

    def __init__(self, mode: str, *, timeout_seconds: float = 10.0) -> None:
        if mode not in test_run_store.VALID_TOOL_MODES:
            raise ValueError(f"invalid tool execution mode: {mode}")
        self.mode = mode
        self.timeout_seconds = timeout_seconds

    def dispatch(self, tool_name: str, tool_config: dict[str, Any] | None = None) -> dict[str, Any]:
        start = time.perf_counter()
        tool_config = tool_config or {}
        timeout_seconds = float(tool_config.get("timeout_seconds") or self.timeout_seconds)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if self.mode == "dry_run":
            return {
                "mode": "dry_run",
                "tool_name": tool_name,
                "executed": False,
                "timeout_seconds": timeout_seconds,
                "elapsed_ms": round(elapsed_ms, 3),
                "timed_out": False,
                "result": {"success": True, "dry_run": True},
                "tool_config": _tool_config_summary(tool_config),
            }

        return {
            "mode": "live",
            "tool_name": tool_name,
            "executed": False,
            "timeout_seconds": timeout_seconds,
            "elapsed_ms": round(elapsed_ms, 3),
            "timed_out": False,
            "result": {
                "success": False,
                "error": "live tool execution is not enabled for flow tests yet",
            },
            "tool_config": _tool_config_summary(tool_config),
        }


def run_profile_text_test(
    db: DbSession,
    *,
    profile: Profile,
    request: TextTestRequest,
) -> ProfileTestRun:
    """Run a deterministic flow smoke test and persist structured events."""
    started = time.perf_counter()
    run = test_run_store.create_run(
        db,
        profile=profile,
        user_message=request.message,
        tool_execution_mode=request.tool_execution_mode,
        status="running",
    )
    dispatcher = ToolDispatcher(request.tool_execution_mode)

    try:
        config = _profile_config(profile)
        mode = ((config.get("models") or {}).get("mode") or "pipeline").strip().lower()
        test_run_store.append_event(
            db,
            run.id,
            event_type="test_started",
            payload={
                "profile_id": profile.id,
                "profile_name": profile.name,
                "profile_config_hash": run.profile_config_hash,
                "profile_snapshot_at": run.profile_snapshot_at.isoformat() if run.profile_snapshot_at else None,
                "tool_execution_mode": request.tool_execution_mode,
                "message": request.message,
                "caveat": "Flow tests exercise saved profile prompt/graph/tool wiring without LLM, voice, LiveKit room behavior, or external side effects.",
            },
        )

        graph_validation = validate_profile_config(config, get_available_tools(), mode=mode)
        if config.get("editor_mode") == "graph" and graph_validation is not None and graph_validation.valid and mode == "pipeline":
            _run_graph_path(db, run, config, request.message, dispatcher, graph_validation)
        else:
            _run_prompt_path(db, run, config, request.message, dispatcher, graph_validation, mode)
        _assert_not_timed_out(db, run, started)

        test_run_store.append_event(
            db,
            run.id,
            event_type="test_completed",
            payload={
                "status": "completed",
                "tool_execution_mode": request.tool_execution_mode,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )

        return test_run_store.finalize_run(
            db,
            run.id,
            status="completed",
            final_summary={
                "status": "completed",
                "assistant_output": _placeholder_assistant_output(config, request.message),
                "tool_execution_mode": request.tool_execution_mode,
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
                "tool_execution_mode": request.tool_execution_mode,
                "error_type": type(exc).__name__,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )
        return test_run_store.finalize_run(
            db,
            run.id,
            status="failed",
            final_summary={"status": "failed", "error_type": type(exc).__name__},
        ) or run


def _assert_not_timed_out(db: DbSession, run: ProfileTestRun, started: float) -> None:
    elapsed = time.perf_counter() - started
    if elapsed <= TEXT_RUN_TIMEOUT_SECONDS:
        return
    test_run_store.append_event(
        db,
        run.id,
        event_type="timeout",
        severity="error",
        payload={
            "scope": "run",
            "timeout_seconds": TEXT_RUN_TIMEOUT_SECONDS,
            "elapsed_ms": round(elapsed * 1000, 3),
        },
    )
    raise TimeoutError(f"flow test timed out after {TEXT_RUN_TIMEOUT_SECONDS}s")


def _run_prompt_path(
    db: DbSession,
    run: ProfileTestRun,
    config: dict[str, Any],
    message: str,
    dispatcher: ToolDispatcher,
    graph_validation,
    mode: str,
) -> None:
    fallback_reason = "prompt_mode"
    if config.get("editor_mode") == "graph":
        if mode != "pipeline":
            fallback_reason = "graph_realtime_fallback"
        elif graph_validation is None:
            fallback_reason = "graph_missing_or_unusable"
        elif not graph_validation.valid:
            fallback_reason = "graph_validation_failed"

    if fallback_reason != "prompt_mode":
        test_run_store.append_event(
            db,
            run.id,
            event_type="fallback",
            severity="warning",
            payload={
                "reason": fallback_reason,
                "errors": _issues(getattr(graph_validation, "errors", [])),
                "warnings": _issues(getattr(graph_validation, "warnings", [])),
            },
        )

    test_run_store.append_event(
        db,
        run.id,
        event_type="prompt_rendered",
        payload={
            "mode": "prompt",
            "instruction_chars": len(str(config.get("instructions") or "")),
            "message": message,
        },
    )

    for tool_def in _declared_tools(config):
        result = dispatcher.dispatch(tool_def.get("name", ""), tool_def)
        test_run_store.append_event(
            db,
            run.id,
            event_type="tool_call",
            payload=result,
        )

    test_run_store.append_event(
        db,
        run.id,
        event_type="assistant_output",
        payload={"text": _placeholder_assistant_output(config, message)},
    )


def _run_graph_path(
    db: DbSession,
    run: ProfileTestRun,
    config: dict[str, Any],
    message: str,
    dispatcher: ToolDispatcher,
    graph_validation,
) -> None:
    graph = normalize_graph(config.get("graph")) or {"nodes": [], "edges": []}
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    node_by_id = {node.get("id"): node for node in nodes}
    start = next(node for node in nodes if node.get("type") == "start")

    test_run_store.append_event(
        db,
        run.id,
        event_type="graph_validated",
        payload={
            "warnings": _issues(graph_validation.warnings),
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
    )
    _enter_node(db, run, start, message=message)

    for tool_name in start.get("tools", []):
        tool_def = _tool_def_by_name(config, tool_name)
        result = dispatcher.dispatch(tool_name, tool_def)
        test_run_store.append_event(db, run.id, event_type="tool_call", payload=result)
        test_run_store.append_event(
            db,
            run.id,
            event_type="tool_result",
            payload={"tool_name": tool_name, "result": result.get("result")},
        )

    selected_edge = _select_edge(start.get("id"), edges, preferred_trigger="tool_result") or _select_edge(
        start.get("id"), edges, preferred_trigger="user_turn"
    )
    if selected_edge:
        target = node_by_id.get(selected_edge.get("target"))
        test_run_store.append_event(
            db,
            run.id,
            event_type="edge_selected",
            payload={
                "edge_id": selected_edge.get("id"),
                "source": selected_edge.get("source"),
                "target": selected_edge.get("target"),
                "trigger": edge_trigger(selected_edge),
                "condition": selected_edge.get("condition") or "",
            },
        )
        if target:
            _enter_node(db, run, target, message=message)
            if target.get("type") == "handoff":
                test_run_store.append_event(
                    db,
                    run.id,
                    event_type="handoff",
                    payload={"target_node_id": target.get("id"), "target_title": target.get("title")},
                )

    test_run_store.append_event(
        db,
        run.id,
        event_type="assistant_output",
        payload={"text": _placeholder_assistant_output(config, message)},
    )


def _enter_node(db: DbSession, run: ProfileTestRun, node: dict[str, Any], *, message: str) -> None:
    test_run_store.append_event(
        db,
        run.id,
        event_type="node_entered",
        payload={
            "node_id": node.get("id"),
            "node_type": node.get("type"),
            "title": node.get("title") or node.get("id"),
            "prompt_chars": len(str(node.get("prompt") or "")),
            "message": message,
        },
    )


def _select_edge(source_id: str | None, edges: list[dict[str, Any]], *, preferred_trigger: str) -> dict[str, Any] | None:
    for edge in edges:
        if edge.get("source") == source_id and edge_trigger(edge) == preferred_trigger:
            return edge
    return None


def _profile_config(profile: Profile) -> dict[str, Any]:
    try:
        config = json.loads(profile.config_json) if profile.config_json else {}
    except (json.JSONDecodeError, TypeError):
        config = {}
    config.setdefault("name", profile.name)
    return config


def _declared_tools(config: dict[str, Any]) -> list[dict[str, Any]]:
    tools = config.get("tools") or []
    return [tool for tool in tools if isinstance(tool, dict) and tool.get("name")]


def _tool_def_by_name(config: dict[str, Any], name: str) -> dict[str, Any]:
    for tool in _declared_tools(config):
        if tool.get("name") == name:
            return tool
    return {"name": name}


def _tool_config_summary(config: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "name": config.get("name"),
        "description": config.get("description"),
        "method": config.get("method"),
        "endpoint": config.get("endpoint"),
        "parameters": config.get("parameters"),
    }
    return {key: value for key, value in summary.items() if value is not None}


def _issues(issues: list[Any]) -> list[dict[str, str]]:
    return [{"code": issue.code, "message": issue.message} for issue in issues]


def _placeholder_assistant_output(config: dict[str, Any], message: str) -> str:
    name = config.get("name") or config.get("display_name") or "profile"
    return f"[{name}] flow test placeholder output for: {message}"
