"""
Agent Factory — 從 DB 或 YAML profile 動態建立 LiveKit Voice Agent

用法：
    from agent_factory import load_profile, create_agent_class

    profile = load_profile("car_inspection")       # 先查 DB，fallback 到 YAML
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

import json
import logging
import pathlib

import yaml

from livekit.agents import Agent, StopResponse
from agent_tools import build_tools_for_agent, get_available_tools

logger = logging.getLogger("agent-factory")

PROFILES_DIR = pathlib.Path(__file__).parent / "profiles"


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
