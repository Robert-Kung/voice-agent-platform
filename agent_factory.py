"""
Agent Factory — 從 YAML profile 動態建立 LiveKit Voice Agent

用法：
    from agent_factory import load_profile, create_agent_class

    profile = load_profile("car_inspection")       # 讀取 profiles/car_inspection.yaml
    PhoneAgent = create_agent_class(profile)        # 動態建立 Agent class（包含 profile 指定的 tools）

YAML profile 的 tools 區塊示例：
    tools:
      - name: get_current_datetime
      - name: check_business_status
      - name: lookup_qa
      - name: transfer_to_human
      - name: check_weather
        config:
          location: "台北市"
"""

import logging
import pathlib

import yaml

from livekit.agents import Agent
from agent_tools import build_tools_for_agent, get_available_tools

logger = logging.getLogger("agent-factory")

PROFILES_DIR = pathlib.Path(__file__).parent / "profiles"


# ── Profile loading ────────────────────────────────────────


def list_profiles() -> list[str]:
    """列出所有可用的 profile 名稱（不含副檔名）。"""
    return sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))


def load_profile(name: str) -> dict:
    """
    讀取指定 profile YAML，回傳 dict。

    Args:
        name: profile 檔名（不含 .yaml），例如 "car_inspection"
    """
    path = PROFILES_DIR / f"{name}.yaml"
    if not path.exists():
        available = list_profiles()
        raise FileNotFoundError(
            f"Profile '{name}' not found.\n"
            f"Available profiles: {', '.join(available)}\n"
            f"Profiles directory: {PROFILES_DIR}"
        )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Dynamic Agent class creation ───────────────────────────


def create_agent_class(profile: dict):
    """
    根據 profile 動態建立主要 Phone Agent class。

    tools 來源：
    1. 若 profile 有 tools 區塊 → 只建立宣告的 tools（附帶各自 config）
    2. 若 profile 沒有 tools 區塊 → 不附加任何 tool（純對話 agent）

    每個 tool 由 agent_tools.py 的 TOOL_REGISTRY 工廠函式建立。
    """
    agent_instructions = profile.get("instructions", "")
    welcome = profile.get("welcome_message", "您好，請問有什麼可以為您服務的？")

    # 根據 profile 的 tools 宣告建立 tool 方法
    tool_methods = build_tools_for_agent(profile)

    # 建立 Agent subclass（只含 __init__ 和 on_enter）
    class DynamicPhoneAgent(Agent):
        def __init__(self) -> None:
            super().__init__(instructions=agent_instructions)

        async def on_enter(self) -> None:
            await self.session.say(welcome)

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
