"""Fixture-level regression tests for checked-in profile examples."""

from pathlib import Path

import yaml

from runtime.graph import edge_trigger


ROOT = Path(__file__).resolve().parents[2]


def _graph_to_prompt(graph: dict) -> str:
    def title_of(node_id: str) -> str:
        for node in graph["nodes"]:
            if node["id"] == node_id:
                return node.get("title") or node["id"]
        return node_id

    lines: list[str] = []
    global_prompt = (graph.get("global_prompt") or "").strip()
    if global_prompt:
        lines.extend([global_prompt, ""])
    lines.extend([
        "# 對話流程",
        "",
        "以下流程由對話圖（graph）自動攤平生成。判斷目前對話所處的階段，遵循該階段的指示；符合轉移規則時進入下一階段（多條規則依列出順序，先命中者生效）。",
        "",
    ])

    ordered = [
        *[node for node in graph["nodes"] if node["type"] == "start"],
        *[node for node in graph["nodes"] if node["type"] != "start"],
    ]
    for node in ordered:
        marker = ""
        if node["type"] == "start":
            marker = "（入口）"
        elif node["type"] == "end":
            marker = "（結束通話）"
        elif node["type"] == "handoff":
            marker = "（轉接真人：呼叫 transfer_to_human）"
        lines.extend([f"## 階段：{node.get('title') or node['id']}{marker}", ""])

        prompt = (node.get("prompt") or "").strip()
        if prompt:
            lines.extend([prompt, ""])
        if node.get("tools"):
            lines.extend([f"此階段可用工具：{'、'.join(node['tools'])}", ""])

        outgoing = [edge for edge in graph.get("edges", []) if edge["source"] == node["id"]]
        if outgoing:
            lines.append("轉移規則：")
            for edge in outgoing:
                condition = (edge.get("condition") or "").strip()
                if edge_trigger(edge) == "tool_result":
                    when = f"工具回傳後，當「{condition}」" if condition else "工具回傳後"
                else:
                    when = f"當「{condition}」" if condition else "無條件"
                lines.append(f"- {when} → 進入「{title_of(edge['target'])}」")
            lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def test_elevator_repair_graph_instructions_match_flattened_graph():
    profile_path = ROOT / "agents" / "profiles" / "elevator_repair_graph.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))

    assert profile["instructions"] == _graph_to_prompt(profile["graph"])
