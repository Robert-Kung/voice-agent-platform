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

from livekit.agents import Agent, StopResponse
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

    # 自動將 qa_data 嵌入 system instructions（取代 lookup_qa tool）
    # 好處：零額外 tool call 延遲，tokens 在 session 開始時一次載入，後續每輪不增加
    qa_data = profile.get("qa_data", [])
    if qa_data:
        qa_lines = ["\n\n[常見問題知識庫]以下問驗直接用於回答，不需呼叫任何工具："]
        for item in qa_data:
            kw = "、".join(item["keywords"][:3])
            qa_lines.append(f"▸ 關鍵字：{kw}")
            qa_lines.append(f"  回答：{item['answer']}")
        agent_instructions = agent_instructions + "\n".join(qa_lines)
        logger.info("將 %d 筆 QA 嵌入 system instructions（%d chars）", len(qa_data), len(agent_instructions))

    # 根據 profile 的 tools 宣告建立 tool 方法
    tool_methods = build_tools_for_agent(profile)

    class DynamicPhoneAgent(Agent):
        def __init__(self) -> None:
            super().__init__(instructions=agent_instructions)

        async def on_enter(self) -> None:
            if mode == "realtime":
                # Realtime 模式：用 generate_reply() 觸發模型主動說出歡迎詞
                # on_enter 在第一個 model turn 前呼叫，send_client_content 對 3.1 有效
                await self.session.generate_reply(
                    instructions=f"請直接說出以下歡迎語，不要改變內容：「{welcome}」"
                )
            else:
                # Pipeline 模式有獨立 TTS，直接播放
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
