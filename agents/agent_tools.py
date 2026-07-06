"""
Agent Tools Registry — 模組化 Tool 工廠

工具分三層（見 CLAUDE.md）：
  - Tier 1（內建原語）：get_current_time
  - Tier 2（profile 設定）：lookup_qa（qa_mode=tool 時掛）、transfer_to_human（human_operator.enabled 時掛）
  - Tier 3（自定義 HTTP）：make_http_tool — 由 profile.tools 宣告 endpoint 即可

新增 Tier 1 工具的條件極嚴格：必須是「每個 agent 都可能需要」的通用功能。
新增業務功能請走 Tier 3，不要進這檔。
"""

import asyncio
import datetime
import inspect
import ipaddress
import logging
import os
import re
from typing import Annotated, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import aiohttp
from pydantic import Field

from livekit.agents.llm import function_tool
from livekit.agents.voice.events import RunContext

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
    # 此描述會進到 LLM 的 function-calling schema，決定模型何時觸發轉接。
    # 領域中立的預設值，profile 可覆寫成具體觸發情境。
    tool_description = (
        ho.get("tool_description")
        or profile.get("human_operator_tool_description")
        or "轉接真人客服。當使用者明確要求真人、出現無法自動處理的情境、或需要人工介入時呼叫。"
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

    async def transfer_to_human(self: RunContext):
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

    return function_tool(transfer_to_human, description=tool_description)


# ═══════════════════════════════════════════════════════════
# Tier 3 — Generic HTTP Tool
# ═══════════════════════════════════════════════════════════

# 工具/參數名稱必須是合法的 Python identifier，且符合 LLM function-call schema
_VALID_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_VALID_PARAM_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
# ${VAR_NAME} 替換 — 大寫 + 數字 + 底線
_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
_ALLOWED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_ALLOWED_PARAM_TYPES = {"string", "number", "integer", "boolean"}
_ALLOWED_RESPONSE_MODES = {"wait", "quick_ack"}
_DEFAULT_HTTP_TIMEOUT_S = 10.0
# quick_ack 背景 task 的強引用集合 — 防止 create_task 後被 GC 提前回收
_BACKGROUND_HTTP_TASKS: set[asyncio.Task] = set()
_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "metadata.google.internal",      # GCE metadata
    "metadata",
    "169.254.169.254",                # AWS / GCP metadata IP literal
})


def _substitute_env(text: str) -> str:
    """把 '${ENV_NAME}' 替換成環境變數值；找不到的 var 替換為空字串。"""
    def repl(m: re.Match) -> str:
        var = m.group(1)
        val = os.environ.get(var, "")
        if not val:
            logger.warning("env var '%s' is empty/unset (referenced in HTTP tool config)", var)
        return val
    return _ENV_VAR_PATTERN.sub(repl, text)


def _validate_endpoint(url: str) -> None:
    """阻擋 SSRF：scheme 必須 http/https；hostname 不能是 localhost / 私網 IP / metadata。

    純 IP 立刻檢查；hostname 由 caller 或 runtime DNS 處理（不在 load 時做 DNS lookup
    以免拖慢 profile 載入；如有需要可日後加 runtime resolve 檢查）。
    """
    if not url:
        raise ValueError("endpoint is required")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"endpoint scheme must be http/https, got '{parsed.scheme}'")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("endpoint must have a hostname")
    if host in _BLOCKED_HOSTNAMES:
        raise ValueError(f"endpoint hostname '{host}' is blocked")
    # IP literal — 立刻擋私網 / loopback / link-local / multicast
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise ValueError(f"endpoint resolves to non-public IP literal: {ip}")
    except ValueError as e:
        # 不是 IP literal — 是 hostname，pass
        if "non-public IP" in str(e):
            raise


def make_http_tool(profile: dict, config: dict):
    """
    Tier 3 通用 HTTP tool。Admin UI 直接設定，不需寫 Python。

    YAML 範例：
        - name: report_elevator_failure
          description: 當住戶回報電梯故障時呼叫此工具
          endpoint: https://api.example.com/elevator/report
          method: POST                 # 預設 POST
          auth_header: "Bearer ${ELEVATOR_API_KEY}"
          timeout_seconds: 10
          response_mode: wait          # wait（預設）或 quick_ack（fire-and-forget，立即回 ack）
          parameters:
            - name: building
              type: string
              required: true
              description: 棟別（A 棟、B 棟...）
            - name: symptom
              type: string
              description: 故障狀況描述

    回傳格式（給 LLM）：
        成功：{"success": true, ...api 回傳內容}
        失敗：{"success": false, "error": "...", "status": 5xx?}
    """
    name = (config.get("name") or "").strip()
    if not _VALID_TOOL_NAME.match(name):
        raise ValueError(f"invalid HTTP tool name '{name}' (must match {_VALID_TOOL_NAME.pattern})")

    description = config.get("description") or f"呼叫 {name} API"
    endpoint = (config.get("endpoint") or "").strip()
    _validate_endpoint(endpoint)

    method = config.get("method", "POST").upper()
    if method not in _ALLOWED_HTTP_METHODS:
        raise ValueError(f"invalid method '{method}' (allowed: {_ALLOWED_HTTP_METHODS})")

    timeout = float(config.get("timeout_seconds") or _DEFAULT_HTTP_TIMEOUT_S)
    if timeout <= 0 or timeout > 60:
        raise ValueError(f"timeout_seconds must be in (0, 60], got {timeout}")

    response_mode = (config.get("response_mode") or "wait").strip()
    if response_mode not in _ALLOWED_RESPONSE_MODES:
        raise ValueError(
            f"invalid response_mode '{response_mode}' (allowed: {sorted(_ALLOWED_RESPONSE_MODES)})"
        )

    auth_header_raw = config.get("auth_header") or ""
    auth_header_resolved = _substitute_env(auth_header_raw) if auth_header_raw else ""

    # JSON schema for LLM
    properties: dict = {}
    required: list[str] = []
    for p in config.get("parameters", []) or []:
        pname = (p.get("name") or "").strip()
        if not _VALID_PARAM_NAME.match(pname):
            raise ValueError(f"invalid parameter name '{pname}' for tool '{name}'")
        ptype = p.get("type", "string")
        if ptype not in _ALLOWED_PARAM_TYPES:
            raise ValueError(f"invalid parameter type '{ptype}' for '{pname}' (allowed: {_ALLOWED_PARAM_TYPES})")
        prop_schema: dict = {"type": ptype}
        if p.get("description"):
            prop_schema["description"] = p["description"]
        properties[pname] = prop_schema
        if p.get("required"):
            required.append(pname)

    parameters_schema = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }

    async def _parse_response(resp: aiohttp.ClientResponse) -> dict:
        if resp.status >= 400:
            text = await resp.text()
            return {"success": False, "status": resp.status, "error": text[:500]}
        try:
            data = await resp.json()
            if isinstance(data, dict):
                return {"success": True, **data}
            return {"success": True, "data": data}
        except (ValueError, aiohttp.ContentTypeError):
            text = await resp.text()
            return {"success": True, "text": text[:500]}

    # LiveKit SDK 的 prepare_function_arguments 會呼叫 inspect.signature() 和
    # get_type_hints() 來解析函式參數。**kwargs 會讓 SDK 嘗試查找 type_hints['kwargs']
    # 而失敗（KeyError: 'kwargs'）。
    # 解法：使用 **kwargs 實作，但動態 patch __signature__ 和 __annotations__
    # 讓 SDK 看到具名參數。

    _JSON_TO_PYTYPE = {"string": str, "number": float, "integer": int, "boolean": bool}
    param_defs = config.get("parameters", []) or []

    async def _do_request(kwargs_clean: dict) -> dict:
        """單次 HTTP 請求 — wait 與 quick_ack 共用。timeout / 錯誤在 caller 處理。"""
        headers = {"Content-Type": "application/json"}
        if auth_header_resolved:
            headers["Authorization"] = auth_header_resolved
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            if method == "GET":
                async with session.request(method, endpoint, headers=headers, params=kwargs_clean) as resp:
                    return await _parse_response(resp)
            else:
                async with session.request(method, endpoint, headers=headers, json=kwargs_clean) as resp:
                    return await _parse_response(resp)

    async def _background_request(kwargs_clean: dict) -> None:
        """quick_ack 背景執行 — 結果只記 log，不回饋對話，例外不外洩。"""
        try:
            result = await _do_request(kwargs_clean)
            if result.get("success"):
                logger.info("http_tool '%s' (quick_ack) background request succeeded", name)
            else:
                logger.warning(
                    "http_tool '%s' (quick_ack) background request failed: %s",
                    name, {k: result.get(k) for k in ("status", "error")},
                )
        except asyncio.TimeoutError:
            logger.warning("http_tool '%s' (quick_ack) background request timed out after %ss", name, timeout)
        except asyncio.CancelledError:
            logger.warning("http_tool '%s' (quick_ack) background request cancelled before completion", name)
            raise
        except aiohttp.ClientError as e:
            logger.warning("http_tool '%s' (quick_ack) background client error: %s", name, e)
        except Exception:
            logger.exception("http_tool '%s' (quick_ack) background unexpected error", name)

    async def _handler(self, **kwargs) -> dict:
        kwargs_clean = {k: v for k, v in kwargs.items() if v is not None}
        logger.info(
            "http_tool '%s' → %s %s (params=%s, mode=%s)",
            name, method, endpoint, list(kwargs_clean.keys()), response_mode,
        )

        if response_mode == "quick_ack":
            task = asyncio.create_task(_background_request(kwargs_clean))
            _BACKGROUND_HTTP_TASKS.add(task)
            task.add_done_callback(_BACKGROUND_HTTP_TASKS.discard)
            return {
                "success": True,
                "accepted": True,
                "detail": "請求已送出，後端處理中；請告知使用者已收到請求，稍後會完成處理",
            }

        try:
            return await _do_request(kwargs_clean)
        except asyncio.TimeoutError:
            logger.warning("http_tool '%s' timed out after %ss", name, timeout)
            return {
                "success": False,
                "pending": True,
                "error": "timeout",
                "detail": (
                    f"請求已送出但未在 {timeout}s 內收到回應；後端可能仍在處理。"
                    "請告知使用者請求已送出、稍候確認，不要重複提交"
                ),
            }
        except aiohttp.ClientError as e:
            logger.warning("http_tool '%s' client error: %s", name, e)
            return {"success": False, "error": f"連線錯誤：{type(e).__name__}"}
        except Exception as e:
            logger.exception("http_tool '%s' unexpected error", name)
            return {"success": False, "error": f"工具呼叫失敗：{type(e).__name__}"}

    # Patch signature：SDK 的 descriptor binding（__get__）在 Agent instance 上
    # 存取 tool 時會 `params[1:]` 移除第一個參數（假設是 self）。
    # 所以 signature 必須把 self 放在第一位，讓 bind 正確移除它。
    #
    # 用 Annotated[type, Field(description="...")] 把每個參數的 description
    # 傳給 SDK 的 Pydantic model builder。required 參數不設 default。
    sig_params = [inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=RunContext)]
    annotations: dict = {"return": dict, "self": RunContext}
    for p in param_defs:
        pname = p["name"]
        pdesc = p.get("description", "")
        is_required = p.get("required", False)
        pytype = _JSON_TO_PYTYPE.get(p.get("type", "string"), str)

        if is_required:
            annotated_type = Annotated[pytype, Field(description=pdesc)]  # type: ignore[valid-type]
            sig_params.append(
                inspect.Parameter(
                    pname,
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=annotated_type,
                )
            )
        else:
            annotated_type = Annotated[Optional[pytype], Field(description=pdesc)]  # type: ignore[valid-type]
            sig_params.append(
                inspect.Parameter(
                    pname,
                    inspect.Parameter.KEYWORD_ONLY,
                    default=None,
                    annotation=annotated_type,
                )
            )
        annotations[pname] = annotated_type

    _handler.__signature__ = inspect.Signature(sig_params, return_annotation=dict)
    _handler.__annotations__ = annotations
    _handler.__doc__ = description
    _handler.__name__ = name

    # 重要：不可使用 raw_schema= 參數！
    # raw_schema 會讓 SDK 建立 RawFunctionTool，Google format converter 會產生
    # parameters_json_schema（而非 parameters）。Gemini Live API
    # (gemini-2.5-flash-native-audio-preview) 不正確處理 parameters_json_schema，
    # 導致模型看到工具名稱但不知道參數格式 → 幻覺工具呼叫而不實際執行。
    # 使用 name= + description= 讓 SDK 建立 FunctionTool，走 parameters 格式。
    return function_tool(
        _handler,
        name=name,
        description=description,
    )


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

    路由規則：
    - tool_def 有 'endpoint' 欄位 → Tier 3：交給 make_http_tool（不需在 TOOL_REGISTRY 註冊）
    - 否則 → 用 TOOL_REGISTRY 內建 factory

    回傳 dict: tool_name → decorated method
    若 profile 沒有 tools 區塊，回傳空 dict（由 agent_factory 決定預設行為）。
    """
    tools_config = profile.get("tools", [])
    if not tools_config:
        return {}

    built = {}
    for tool_def in tools_config:
        name = tool_def.get("name", "")

        # Tier 3：HTTP tool — 整個 tool_def 當 config 傳入
        if "endpoint" in tool_def:
            try:
                built[name] = make_http_tool(profile, tool_def)
                logger.info("Built Tier 3 HTTP tool: %s → %s", name, tool_def["endpoint"])
            except ValueError as e:
                logger.warning(
                    "Skipping invalid HTTP tool '%s' in profile '%s': %s",
                    name, profile.get("name", "?"), e,
                )
            continue

        # Tier 1 / Tier 2：用內建 registry
        config = tool_def.get("config", {})
        factory = TOOL_REGISTRY.get(name)
        if not factory:
            available = ", ".join(TOOL_REGISTRY.keys())
            logger.warning(
                "Unknown tool '%s' in profile '%s'. Available built-ins: %s. "
                "(Tier 3 HTTP tools must include an 'endpoint' field.)",
                name, profile.get("name", "?"), available,
            )
            continue

        built[name] = factory(profile, config)
        logger.debug("Built tool: %s", name)

    return built
