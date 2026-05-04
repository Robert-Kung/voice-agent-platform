"""
Agent Tools Registry — 模組化 Tool 工廠

工具分三層（見 CLAUDE.md）：
  - Tier 1（內建原語）：get_current_time
  - Tier 2（profile 設定）：lookup_qa（qa_mode=tool 時掛）、transfer_to_human（human_operator.enabled 時掛）
  - Tier 3（自定義 HTTP）：見 make_http_tool（待實作）

新增 Tier 1 工具的條件極嚴格：必須是「每個 agent 都可能需要」的通用功能。
新增業務功能請走 Tier 3（HTTP tool），不要進這檔。
"""

import datetime
import logging
from zoneinfo import ZoneInfo

from livekit.agents.llm import function_tool

logger = logging.getLogger("agent-tools")


# ═══════════════════════════════════════════════════════════
# 內建 Tools
# ═══════════════════════════════════════════════════════════


# ── 1. get_current_time ────────────────────────────────────

def make_get_current_time(profile: dict, config: dict):
    """只回傳目前時間與星期，讓 LLM 使用 system prompt 中的營業時間自行判斷。"""
    tz = ZoneInfo(config.get("timezone", profile.get("timezone", "Asia/Taipei")))

    @function_tool
    async def get_current_time(self) -> dict:
        """
        取得目前台北時間與星期。
        當使用者詢問任何服務是否營業、幾點開門、幾點關門時呼叫。
        回傳後請依 system prompt 中的營業時間自行判斷並回答。
        """
        now = datetime.datetime.now(tz)
        result = {
            "current_time": now.strftime("%H:%M"),
            "weekday": now.strftime("%A"),  # 英文全名，如 Monday / Saturday
        }
        logger.info("get_current_time: %s %s (%s)", result["current_time"], result["weekday"], now.strftime("%Z%z"))
        return result

    return get_current_time


# ── 2. lookup_qa ──────────────────────────────────────────

def make_lookup_qa(profile: dict, config: dict):
    """在 qa_data 中搜尋匹配答案。需要 profile 中有 qa_data 定義。"""
    qa_data = profile.get("qa_data", [])

    @function_tool
    async def lookup_qa(self, question_intent: str) -> dict:
        """
        查詢已建檔的 QA，涵蓋汽車代檢、洗車、加油三項服務。
        當使用者詢問任一服務的細節（費用、流程、規定、注意事項等）時呼叫。

        Args:
            question_intent: 使用者問題的意圖摘要（中文），需包含服務類型，
                例如「驗車要攜帶什麼文件」、「洗車費用多少」、「加油有哪些油種」
        """
        logger.info("lookup_qa: intent=%r", question_intent)
        for item in qa_data:
            keywords = item.get("keywords", [])
            if any(kw in question_intent for kw in keywords):
                logger.info("lookup_qa: hit keywords=%s", keywords)
                return {"found": True, "answer_text": item["answer"]}
        logger.info("lookup_qa: no match found")
        return {"found": False, "answer_text": ""}

    return lookup_qa


# ── 3. transfer_to_human ─────────────────────────────────

def make_transfer_to_human(profile: dict, config: dict):
    """轉接真人服務（由 agent_factory 在 human_operator.enabled 時自動掛載）。

    讀取順序：
      1. profile.human_operator.{instructions, greeting, voice, transfer_message}（新 schema）
      2. profile.human_operator_{instructions, greeting, voice}（舊散落欄位，向後相容）
      3. 內建預設值
    """
    from livekit.agents import Agent, StopResponse, llm as _llm

    ho = profile.get("human_operator") if isinstance(profile.get("human_operator"), dict) else {}

    instructions = (
        ho.get("instructions")
        or profile.get("human_operator_instructions")
        or config.get("instructions")
        or "你是服務人員，詢問有什麼可以協助的。"
    )
    greeting = (
        ho.get("greeting")
        or profile.get("human_operator_greeting")
        or config.get("greeting")
        or "告知已轉接成功，詢問有什麼可以協助的。"
    )
    transfer_msg = (
        ho.get("transfer_message")
        or config.get("transfer_message")
        or "感謝您的耐心等候，現在為您轉接服務人員，請稍候。"
    )
    # 預設用男聲 Puck，與主 Agent 的女聲 Kore 區別，讓使用者聽到切換
    human_voice = (
        ho.get("voice")
        or profile.get("human_operator_voice")
        or config.get("voice")
        or "Puck"
    )

    def _build_human_realtime_model(session_llm):
        """從目前 session 的 RealtimeModel 複製設定，但替換聲音。

        handoff 後新 AgentActivity 會用此 model 建立新的 Gemini WebSocket，
        使用者會聽到不同聲音，確認已切換到門市人員。
        """
        try:
            from google.genai import types as _genai_types

            # 從現有 model 取得設定
            opts = session_llm._opts
            model_name = opts.model

            # 動態判斷是否為 TextInputRealtimeModel（攔截音頻的子類）
            model_cls = type(session_llm)

            human_model = model_cls(
                model=model_name,
                voice=human_voice,
                temperature=opts.temperature,
                thinking_config=opts.thinking_config,
                input_audio_transcription=opts.input_audio_transcription,
                realtime_input_config=opts.realtime_input_config,
            )
            logger.info(
                "Built HumanOperator realtime model: %s voice=%s (cls=%s)",
                model_name, human_voice, model_cls.__name__,
            )
            return human_model
        except Exception:
            logger.exception("Failed to build HumanOperator realtime model, falling back to session LLM")
            return None

    class _HumanOperator(Agent):
        def __init__(self, chat_ctx=None, llm_override=None):
            kwargs = dict(instructions=instructions, chat_ctx=chat_ctx)
            if llm_override is not None:
                kwargs["llm"] = llm_override
            super().__init__(**kwargs)

        async def on_enter(self) -> None:
            await self.session.generate_reply(instructions=greeting)

        async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
            """Realtime 模式：攔截 STT 文字轉發給 Gemini，與主 Agent 同邏輯。

            問題背景：TextInputRealtimeModel 攔截了 push_audio（no-op），
            Gemini 收不到音頻。SDK 對 RealtimeModel 會在
            on_user_turn_completed 後將 user_message 設為 None，
            導致 generate_reply(user_input=None) 不送任何內容給 Gemini。

            若 _HumanOperator 不覆寫此方法，handoff 後使用者說話
            Gemini 完全聽不到，對話斷裂。
            """
            # Pipeline 模式：session.llm 是 LLM 類型，交由 SDK 預設流程
            if not isinstance(self.session.llm, _llm.RealtimeModel):
                return

            user_text = new_message.text_content
            if user_text:
                logger.info(
                    "HumanOperator realtime: forwarding STT text to Gemini (%d chars)",
                    len(user_text),
                )
                self.session.generate_reply(user_input=user_text)
            else:
                logger.warning("HumanOperator realtime: empty STT transcript, skipping reply")
            raise StopResponse()

    _HumanOperator.__name__ = f"HumanOperator_{profile.get('name', 'unknown')}"

    @function_tool
    async def transfer_to_human(self):
        """
        轉接真人接聽。
        僅在無法對應任何已建檔 QA、意圖不明、或使用者明確要求轉接時使用。
        """
        # Realtime 模式：建立不同聲音的 model，讓使用者聽到切換
        llm_override = None
        if isinstance(self.session.llm, _llm.RealtimeModel):
            llm_override = _build_human_realtime_model(self.session.llm)

        logger.info(
            "transfer_to_human: handing off to %s (voice=%s)",
            _HumanOperator.__name__,
            human_voice if llm_override else "session_default",
        )
        return _HumanOperator(chat_ctx=self.chat_ctx, llm_override=llm_override), transfer_msg

    return transfer_to_human




# ═══════════════════════════════════════════════════════════
# Tool Registry
# ═══════════════════════════════════════════════════════════

TOOL_REGISTRY: dict[str, callable] = {
    "get_current_time": make_get_current_time,
    "lookup_qa": make_lookup_qa,                  # 條件性掛載：profile.qa_mode == "tool" 才上
    "transfer_to_human": make_transfer_to_human,  # 條件性掛載：profile.human_operator.enabled 才上
}


def get_available_tools() -> list[str]:
    """列出所有已註冊的 tool 名稱。"""
    return list(TOOL_REGISTRY.keys())


def build_tools_for_agent(profile: dict) -> dict[str, object]:
    """
    根據 profile 的 tools 宣告，建立對應的 @function_tool 方法。

    回傳 dict: tool_name → decorated method

    若 profile 沒有 tools 區塊，回傳空 dict（由 agent_factory 決定預設行為）。
    """
    tools_config = profile.get("tools", [])
    if not tools_config:
        return {}

    built = {}
    for tool_def in tools_config:
        name = tool_def["name"]
        config = tool_def.get("config", {})

        factory = TOOL_REGISTRY.get(name)
        if not factory:
            available = ", ".join(TOOL_REGISTRY.keys())
            logger.warning(
                "Unknown tool '%s' in profile '%s'. Available: %s",
                name, profile.get("name", "?"), available,
            )
            continue

        built[name] = factory(profile, config)
        logger.debug("Built tool: %s", name)

    return built
