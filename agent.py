import json
import logging
import os
import sys

from dotenv import load_dotenv
from livekit.agents import (
    AgentSession,
    JobContext,
    RoomInputOptions,
    WorkerOptions,
    cli,
    inference,
    llm,
    stt,
    tts,
)
from livekit.plugins import google, noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents import metrics, MetricsCollectedEvent, AgentStateChangedEvent

from agent_factory import load_profile, create_agent_class, list_profiles

from google.genai import types as genai_types

logger = logging.getLogger("agent")

load_dotenv(".env")

# ── Profile 選擇 ──────────────────────────────────────────
# 支援三種方式選擇 profile（優先順序由高到低）：
#
# 1. Room metadata — 部署在 Cloud 時，前端建房間時帶上 metadata
#    例：{"profile": "restaurant"}
#    → 同一個 agent 可服務不同場域，免費版只需部署一個 agent
#
# 2. 命令列參數 --profile / -p
#    例：uv run agent.py console --profile restaurant
#
# 3. 環境變數 AGENT_PROFILE
#    例：AGENT_PROFILE=restaurant uv run agent.py console
#
# 預設：car_inspection
# ───────────────────────────────────────────────────────────

DEFAULT_PROFILE = "car_inspection"

# ── Agent 模式 ─────────────────────────────────────────────
# AGENT_MODE 控制語音處理架構：
#   "pipeline"  — STT → LLM → TTS 分離式管線（預設，使用 LiveKit Inference）
#   "realtime"  — Google Gemini Live API 全端對端（audio-in → audio-out）
#
# 切換方式：
#   AGENT_MODE=realtime uv run agent.py console -p car_inspection
#   lk agent update-secrets --secrets "AGENT_MODE=realtime"
# ───────────────────────────────────────────────────────────
AGENT_MODE = os.environ.get("AGENT_MODE", "pipeline")


def _get_cli_profile_name() -> str:
    """從 sys.argv 或環境變數取得 profile 名稱（啟動時的預設值）。"""
    for i, arg in enumerate(sys.argv):
        if arg in ("--profile", "-p") and i + 1 < len(sys.argv):
            name = sys.argv.pop(i + 1)
            sys.argv.pop(i)
            return name
    return os.environ.get("AGENT_PROFILE", DEFAULT_PROFILE)


def _get_runtime_profile_name(ctx: JobContext) -> str:
    """
    從 Room metadata 動態決定 profile（Cloud 部署用）。

    前端建房間時可帶：
      metadata: '{"profile": "restaurant"}'

    若 metadata 不存在或無 profile 欄位，fallback 到 CLI/env 設定。
    """
    # 1. 先嘗試從 room metadata 讀取
    try:
        room_metadata = ctx.job.room.metadata
        if room_metadata:
            data = json.loads(room_metadata)
            profile_name = data.get("profile")
            if profile_name and profile_name in list_profiles():
                logger.info("Profile from room metadata: %s", profile_name)
                return profile_name
            elif profile_name:
                logger.warning(
                    "Room metadata requested profile '%s' but not found. "
                    "Available: %s. Falling back to default.",
                    profile_name, ", ".join(list_profiles()),
                )
    except (json.JSONDecodeError, AttributeError) as e:
        logger.debug("No valid profile in room metadata: %s", e)

    # 2. 嘗試從 agent dispatch metadata 讀取
    try:
        job_metadata = ctx.job.metadata
        if job_metadata:
            data = json.loads(job_metadata)
            profile_name = data.get("profile")
            if profile_name and profile_name in list_profiles():
                logger.info("Profile from dispatch metadata: %s", profile_name)
                return profile_name
    except (json.JSONDecodeError, AttributeError):
        pass

    # 3. Fallback: CLI / env
    return CLI_PROFILE_NAME


CLI_PROFILE_NAME = _get_cli_profile_name()

logger.info("Default profile: %s", CLI_PROFILE_NAME)
logger.info("Agent mode: %s", AGENT_MODE)
logger.info("Available profiles: %s", ", ".join(list_profiles()))


async def entrypoint(ctx: JobContext):
    # ── 動態選擇 profile（支援 room metadata 切換）──
    profile_name = _get_runtime_profile_name(ctx)
    profile = load_profile(profile_name)
    PhoneAgent = create_agent_class(profile, mode=AGENT_MODE)
    logger.info("Session using profile: %s (%s), mode: %s", profile.get("name"), profile_name, AGENT_MODE)

    vad = silero.VAD.load()

    if AGENT_MODE == "realtime":
        # ── Google Gemini Live API（全端對端 audio-in → audio-out）──
        # 需要 GOOGLE_API_KEY 環境變數（不走 LiveKit Inference）
        # Live API 專用模型（注意：gemini-2.5-flash 是 chat 模型，不支援 Live API）
        # Gemini Live API 可用聲音（Nova 是 OpenAI 聲音，Gemini 不支援）：
        #   女聲：Aoede, Kore, Laomedeia, Zephyr, Callirrhoe, Sulafat…
        #   男聲：Puck, Charon, Fenrir, Rasalgethi, Sadaltager…
        realtime_voice = os.environ.get("GOOGLE_REALTIME_VOICE", "Kore")
        realtime_model = os.environ.get(
            "GOOGLE_REALTIME_MODEL",
            "gemini-2.5-flash-native-audio-preview-12-2025",  # plugin 預設（Gemini API）
            # Vertex AI 備選："gemini-live-2.5-flash-native-audio"
            # gemini-3.1-flash-live-preview 是 Live API 最新模型，尚未在 plugin 預設中更新
        )
        logger.info("Realtime mode: model=%s, voice=%s", realtime_model, realtime_voice)
        
        session = AgentSession(
            llm=google.realtime.RealtimeModel(
                model=realtime_model,
                voice=realtime_voice,
                temperature=0.8,
                # NON_BLOCKING：tool call 時模型可繼續說橋接語，不會靜音等待
                # WHEN_IDLE：等模型說完當前語音再插入 tool 結果（避免截斷）
                tool_behavior=genai_types.Behavior.NON_BLOCKING,
                tool_response_scheduling=genai_types.FunctionResponseScheduling.WHEN_IDLE,
            ),
        )
    else:
        # ── Pipeline 模式（STT → LLM → TTS，使用 LiveKit Inference）──
        session = AgentSession(
            llm=llm.FallbackAdapter(
                [
                    inference.LLM(model="google/gemini-3.1-flash-lite"),
                    inference.LLM(model="openai/gpt-4.1-mini"),
                ]
            ),
            stt=stt.FallbackAdapter(
                [
                    inference.STT(model="elevenlabs/scribe_v2_realtime", language="zh"),
                    inference.STT(model="deepgram/nova-2", language="zh-TW"),
                ]
            ),
            tts=tts.FallbackAdapter(
                [
                    inference.TTS(model="cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc", language="zh"),
                    inference.TTS(model="elevenlabs/eleven_multilingual_v2", language="zh"),
                ]
            ),
            vad=vad,
            turn_detection=MultilingualModel(),
            preemptive_generation=True,
        )

    usage_collector = metrics.UsageCollector()
    last_eou_metrics: metrics.EOUMetrics | None = None

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        nonlocal last_eou_metrics
        if ev.metrics.type == "eou_metrics":
            last_eou_metrics = ev.metrics
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info("Usage summary: %s", summary)

    ctx.add_shutdown_callback(log_usage)

    @session.on("agent_state_changed")
    def _on_agent_state_changed(ev: AgentStateChangedEvent):
        if (
            ev.new_state == "speaking"
            and last_eou_metrics
            and session.current_speech
            and last_eou_metrics.speech_id == session.current_speech.id
        ):
            delta = ev.created_at - last_eou_metrics.timestamp
            logger.info("Time to first audio frame: %sms", delta * 1000)

    await ctx.connect()

    await session.start(
        agent=PhoneAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="voice-assistant"))
