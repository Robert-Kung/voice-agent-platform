"""
Agent Tools Registry — 模組化 Tool 工廠

每個 tool 是一個工廠函式，接收 (profile, config) 回傳 @function_tool 裝飾的 async method。
YAML profile 透過 tools 區塊宣告要啟用哪些 tool 以及各自的 config。

新增 tool 步驟：
1. 寫一個 make_xxx(profile, config) 函式，回傳 @function_tool 裝飾的 method
2. 加入 TOOL_REGISTRY
3. 在 YAML profile 的 tools 區塊宣告即可使用

目前內建 tools：
  - get_current_datetime    取得當前日期時間
  - check_business_status   依 services 定義判斷營業狀態
  - lookup_qa               在 qa_data 中關鍵字匹配
  - transfer_to_human       轉接真人服務
  - check_weather           查詢天氣（模擬 / 可接 API）
  - search_menu             搜尋菜單 / 產品目錄
  - book_appointment        預約登記（收集資訊後轉接）
  - calculate_price         依規則計算費用
"""

import datetime
import logging
from zoneinfo import ZoneInfo

from livekit.agents.llm import function_tool

logger = logging.getLogger("agent-tools")


# ═══════════════════════════════════════════════════════════
# 內建 Tools
# ═══════════════════════════════════════════════════════════


# ── 1. get_current_datetime ────────────────────────────────

def make_get_current_datetime(profile: dict, config: dict):
    """取得來電當下的日期時間。"""
    tz = ZoneInfo(config.get("timezone", profile.get("timezone", "Asia/Taipei")))

    @function_tool
    async def get_current_datetime(self) -> dict:
        """取得來電當下的日期、時間（HH:MM）與星期（Mon/Tue/Wed/Thu/Fri/Sat/Sun）。"""
        now = datetime.datetime.now(tz)
        return {
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
            "weekday": now.strftime("%a"),
        }

    return get_current_datetime


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


# ── 2. check_business_status ──────────────────────────────

def _parse_time(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _eval_business_status(profile: dict, service_type: str) -> dict:
    """根據 profile.services 判斷指定服務此刻是否營業。"""
    tz = ZoneInfo(profile.get("timezone", "Asia/Taipei"))
    now = datetime.datetime.now(tz)
    current_minutes = now.hour * 60 + now.minute
    weekday = now.weekday()
    current_time_str = now.strftime("%H:%M")
    logger.info(
        "check_business_status: service=%s local_time=%s weekday=%s tz=%s",
        service_type, now.strftime("%Y-%m-%d %H:%M %Z%z"), now.strftime("%a"), tz,
    )

    services = profile.get("services", {})
    svc = services.get(service_type)
    if not svc:
        return {
            "is_open": False,
            "current_time": current_time_str,
            "service_hours_text": "查無此服務類型。",
        }

    if svc.get("always_open"):
        return {
            "is_open": True,
            "current_time": current_time_str,
            "service_hours_text": svc.get("hours_text", ""),
        }

    closed_days = svc.get("closed_days", [])
    if weekday in closed_days:
        hours_text = svc.get("hours_text", {})
        text = hours_text if isinstance(hours_text, str) else hours_text.get("closed", "今日休息。")
        return {
            "is_open": False,
            "current_time": current_time_str,
            "service_hours_text": text,
        }

    schedule = svc.get("schedule", {})
    is_open = False
    close_time_str = ""

    if weekday == 5 and "saturday" in schedule:
        slot = schedule["saturday"]
        start, end = _parse_time(slot["start"]), _parse_time(slot["end"])
        is_open = start <= current_minutes < end
        close_time_str = slot["end"] if is_open else ""
        hours_text = svc.get("hours_text", {})
        text = hours_text if isinstance(hours_text, str) else hours_text.get("saturday", hours_text.get("weekday", ""))
        result = {
            "is_open": is_open,
            "current_time": current_time_str,
            "service_hours_text": text,
        }
        if is_open and close_time_str:
            result["closes_at"] = close_time_str
        return result

    for slot_name, slot in schedule.items():
        if slot_name == "saturday":
            continue
        start, end = _parse_time(slot["start"]), _parse_time(slot["end"])
        if start <= current_minutes < end:
            is_open = True
            close_time_str = slot["end"]
            break

    hours_text = svc.get("hours_text", {})
    text = hours_text if isinstance(hours_text, str) else hours_text.get("weekday", "")
    result = {
        "is_open": is_open,
        "current_time": current_time_str,
        "service_hours_text": text,
    }
    if is_open and close_time_str:
        result["closes_at"] = close_time_str
    return result


def make_check_business_status(profile: dict, config: dict):
    """依服務別判斷營業狀態。需要 profile 中有 services 定義。"""
    _profile = profile
    # 從 config 中取得可用的 service types，用於 docstring
    service_types = list(profile.get("services", {}).keys())
    description = (
        f"依服務別判斷目前是否營業，回傳 is_open 與服務時間說明。"
        f"可用的 service_type: {', '.join(service_types)}"
    )

    @function_tool(description=description)
    async def check_business_status(self, service_type: str) -> dict:
        """依服務別判斷目前是否營業。"""
        result = _eval_business_status(_profile, service_type)
        logger.info("check_business_status result: %s", result)
        return result

    return check_business_status


# ── 3. lookup_qa ──────────────────────────────────────────

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


# ── 4. transfer_to_human ─────────────────────────────────

def make_transfer_to_human(profile: dict, config: dict):
    """轉接真人服務。

    config 範例（YAML profile 的 tools 區塊）：
      - name: transfer_to_human
        config:
          voice: "Puck"           # Handoff 後使用不同聲音，讓使用者感知已切換
          transfer_message: "正在為您轉接服務人員，請稍候。"
    """
    from livekit.agents import Agent, StopResponse, llm as _llm

    instructions = profile.get(
        "human_operator_instructions",
        config.get("instructions", "你是服務人員，詢問有什麼可以協助的。"),
    )
    greeting = profile.get(
        "human_operator_greeting",
        config.get("greeting", "告知已轉接成功，詢問有什麼可以協助的。"),
    )
    transfer_msg = config.get(
        "transfer_message",
        "感謝您的耐心等候，現在為您轉接服務人員，請稍候。",
    )

    # Realtime 模式下 _HumanOperator 使用的聲音
    # 優先順序：config.voice > profile.human_operator_voice > 預設 "Puck"
    # 預設用男聲 Puck，與主 Agent 的女聲 Kore 區別，讓使用者聽到切換
    human_voice = config.get(
        "voice",
        profile.get("human_operator_voice", "Puck"),
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


# ── 5. check_weather ──────────────────────────────────────

def make_check_weather(profile: dict, config: dict):
    """
    查詢天氣狀況。

    config 範例：
      location: "台北市"
      conditions:
        - condition: "晴天"
          temp_range: [25, 35]
          advice: "今天天氣晴朗，適合戶外活動。"
        - condition: "雨天"
          temp_range: [18, 25]
          advice: "今天有雨，請攜帶雨具。"
      api_url: ""   # 可選：接真實天氣 API
    """
    default_location = config.get("location", "本地")
    conditions = config.get("conditions", [])

    @function_tool
    async def check_weather(self, location: str = "") -> dict:
        """
        查詢指定地點的天氣狀況，用於提供天氣相關建議。

        Args:
            location: 地點名稱（可選，預設使用營業地點）
        """
        loc = location or default_location

        # 如果有設定 API URL，可以接真實 API
        api_url = config.get("api_url", "")
        if api_url:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        api_url,
                        params={"location": loc},
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            return await resp.json()
            except Exception as e:
                logger.warning("Weather API failed: %s", e)

        # 無 API 或 API 失敗：使用 config 中的靜態天氣資料
        if conditions:
            # 依時間模擬：用當天日期 hash 選一個 condition
            import hashlib
            tz = ZoneInfo(profile.get("timezone", "Asia/Taipei"))
            today = datetime.datetime.now(tz).strftime("%Y-%m-%d")
            idx = int(hashlib.md5(today.encode()).hexdigest(), 16) % len(conditions)
            cond = conditions[idx]
            return {
                "location": loc,
                "condition": cond.get("condition", "晴天"),
                "temperature": f"{cond.get('temp_range', [25, 30])[0]}~{cond.get('temp_range', [25, 30])[1]}°C",
                "advice": cond.get("advice", ""),
            }

        return {
            "location": loc,
            "condition": "資料不足",
            "temperature": "未知",
            "advice": "目前無法取得天氣資訊，建議出門前查看氣象預報。",
        }

    return check_weather


# ── 6. search_menu ────────────────────────────────────────

def make_search_menu(profile: dict, config: dict):
    """
    搜尋菜單 / 產品目錄。

    config 範例：
      categories:
        - name: "主餐"
          items:
            - name: "三杯雞"
              price: 280
              description: "經典台式三杯雞，香氣四溢"
            - name: "紅燒獅子頭"
              price: 320
    """
    categories = config.get("categories", [])

    @function_tool
    async def search_menu(self, keyword: str) -> dict:
        """
        搜尋菜單或產品目錄中的品項。

        Args:
            keyword: 搜尋關鍵字（品名、類別或描述）
        """
        results = []
        for cat in categories:
            cat_name = cat.get("name", "")
            for item in cat.get("items", []):
                item_name = item.get("name", "")
                item_desc = item.get("description", "")
                if (
                    keyword in item_name
                    or keyword in item_desc
                    or keyword in cat_name
                ):
                    results.append({
                        "category": cat_name,
                        "name": item_name,
                        "price": item.get("price"),
                        "description": item_desc,
                    })

        if results:
            return {"found": True, "items": results, "count": len(results)}
        return {"found": False, "items": [], "count": 0}

    return search_menu


# ── 7. book_appointment ──────────────────────────────────

def make_book_appointment(profile: dict, config: dict):
    """
    預約登記：收集必要資訊後轉接或記錄。

    config 範例：
      required_fields: ["姓名", "電話", "希望時段"]
      confirmation_message: "已為您記錄預約資訊，將由專人確認後回電。"
      auto_transfer: true   # 收集完後是否自動轉接真人
    """
    required_fields = config.get("required_fields", ["姓名", "希望時段"])
    confirmation_msg = config.get(
        "confirmation_message",
        "已記錄您的預約資訊，將由服務人員確認後與您聯繫。",
    )

    fields_desc = "、".join(required_fields)

    @function_tool
    async def book_appointment(self, customer_info: str) -> dict:
        f"""
        記錄預約登記資訊。請先向使用者收集以下資訊：{fields_desc}，
        收集完畢後呼叫此工具。

        Args:
            customer_info: 使用者提供的預約資訊（含{fields_desc}）
        """
        # 檢查必要欄位是否都有提到
        missing = [f for f in required_fields if f not in customer_info]
        if missing:
            return {
                "success": False,
                "message": f"尚缺以下資訊：{'、'.join(missing)}，請向使用者確認。",
            }
        return {
            "success": True,
            "message": confirmation_msg,
            "recorded_info": customer_info,
        }

    return book_appointment


# ── 8. calculate_price ────────────────────────────────────

def make_calculate_price(profile: dict, config: dict):
    """
    依規則計算費用。

    config 範例：
      price_rules:
        - name: "一般洗車"
          base_price: 300
          description: "一般外觀清洗"
        - name: "精緻洗車"
          base_price: 600
          description: "內外精緻清洗"
      currency: "TWD"
      note: "實際費用以現場報價為準"
    """
    price_rules = config.get("price_rules", [])
    currency = config.get("currency", "TWD")
    note = config.get("note", "")

    @function_tool
    async def calculate_price(self, item_name: str) -> dict:
        """
        查詢項目費用或報價。

        Args:
            item_name: 要查詢的項目名稱
        """
        for rule in price_rules:
            if rule["name"] in item_name or item_name in rule["name"]:
                result = {
                    "found": True,
                    "item": rule["name"],
                    "price": rule["base_price"],
                    "currency": currency,
                    "description": rule.get("description", ""),
                }
                if note:
                    result["note"] = note
                return result

        return {
            "found": False,
            "message": "查無此項目費用，建議洽詢服務人員。",
        }

    return calculate_price


# ═══════════════════════════════════════════════════════════
# Tool Registry
# ═══════════════════════════════════════════════════════════

TOOL_REGISTRY: dict[str, callable] = {
    "get_current_datetime": make_get_current_datetime,
    "get_current_time": make_get_current_time,        # 輕量版：只回傳時間，業務邏輯由 LLM 從 system prompt 判斷
    "check_business_status": make_check_business_status,
    "lookup_qa": make_lookup_qa,
    "transfer_to_human": make_transfer_to_human,
    "check_weather": make_check_weather,
    "search_menu": make_search_menu,
    "book_appointment": make_book_appointment,
    "calculate_price": make_calculate_price,
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
