import json
import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from livekit.agents import (
    AgentSession,
    JobContext,
    TurnHandlingOptions,
    WorkerOptions,
    cli,
    inference,
    llm,
    room_io,
    stt,
    tts,
)
from livekit.plugins import google, noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents import metrics, MetricsCollectedEvent, AgentStateChangedEvent

from agent_factory import load_profile_with_id, create_agent_class, list_profiles

from google.genai import types as genai_types

logger = logging.getLogger("agent")

# DB integration — graceful fallback if DB layer can't be initialized.
# Import/init failures must be visible (not silent) so ops can tell why the
# agent is running without session tracking.
try:
    from db.engine import init_db, get_session_factory
    from db import session_store, profile_store
    from db.cost import compute_cost
    init_db()
    _db_available = True
except Exception:
    _db_available = False
    logger.exception("DB layer unavailable; session tracking disabled")


# ── TextInputRealtimeModel ─────────────────────────────────
# 解決 Gemini Live API 音頻上下文累積造成的延遲遞增問題。
#
# 問題原因：Gemini 接收原始音頻 → 音頻 token 隨對話時間累積
#   → 回覆延遲從 1-2 秒遞增到 20-30 秒（已在所有 observability 資料中確認）
#
# 解法：攔截 push_audio / start_user_activity，不向 Gemini 傳送音頻，
#   改由 STT（Deepgram）轉錄文字後，透過 send_client_content 傳入。
#   文字 token 遠小於音頻 token，延遲可保持穩定。
#
# 完整信號流：
#   [語音] → Silero VAD → Deepgram STT → MultilingualModel EOU
#         → on_user_turn_completed → session.generate_reply(user_input=text)
#         → Gemini（文字輸入）→ 語音輸出
# ───────────────────────────────────────────────────────────

class TextInputRealtimeModel(google.realtime.RealtimeModel):
    """封裝 RealtimeModel，攔截音頻推送，改為純文字輸入模式。"""

    def session(self):
        sess = super().session()
        # 不向 Gemini 推送音頻（避免 audio token 累積導致延遲遞增）
        sess.push_audio = lambda frame: None
        # 不發送 activity_start/end 信號（無音頻時不需要活動信號）
        sess.start_user_activity = lambda: None
        return sess

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
    profile, db_profile_id = load_profile_with_id(profile_name)
    PhoneAgent = create_agent_class(profile, mode=AGENT_MODE)
    logger.info("Session using profile: %s (%s), mode: %s", profile.get("name"), profile_name, AGENT_MODE)

    # ── DB session tracking ──
    db_session_id: str | None = None
    session_started_at = datetime.now(timezone.utc)
    if _db_available:
        try:
            factory = get_session_factory()
            with factory() as db:
                room_name = ctx.job.room.name if ctx.job.room else "unknown"
                db_sess = session_store.create_session(
                    db,
                    room_name=room_name,
                    profile_id=db_profile_id,
                )
                db_session_id = db_sess.id
                session_started_at = db_sess.started_at
                logger.info("DB session created: %s", db_session_id)
        except Exception:
            logger.exception("Failed to create DB session")

    vad = silero.VAD.load(
        activation_threshold=0.7,    # 預設 0.5；調高減少 SIP echo/雜音誤觸
        min_silence_duration=1.0,    # 預設 0.55s；調長避免 agent 說話停頓被誤判 EOU
        min_speech_duration=0.15,    # 預設 0.05s；過濾短暫雜音
    )

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
            "gemini-2.5-flash-native-audio-preview-12-2025",  # 2.5：generate_reply() 正常
            # "gemini-3.1-flash-live-preview"  # 3.1：plugin 1.5.1 的 generate_reply() 用
            #   send_client_content，3.1 完全封鎖此 API → 任何情況都會 1007
            #   待 plugin 改用 send_realtime_input 後再切回
        )
        logger.info("Realtime mode: model=%s, voice=%s", realtime_model, realtime_voice)

        # 2.5：thinkingBudget=0 完全關閉 thinking → 最低延遲，等同 3.1 minimal 效果
        # 3.1：改用 thinkingLevel="minimal"（3.1 不支援 thinkingBudget）
        # 注意：3.1 仍不可用，generate_reply() 走 send_client_content，3.1 完全封鎖 → 1007
        thinking_cfg = genai_types.ThinkingConfig(thinkingBudget=0)

        # SIP Echo 解法：關閉 Gemini VAD，改由 LiveKit Silero VAD 控制
        # 必須保持 disabled=True 以確保 SDK 不跳過 on_user_turn_completed 回調
        # （SDK 在 turn_detection=True 時會直接 return，不觸發文字轉發流程）
        #
        # 架構：TextInputRealtimeModel 攔截音頻 → 只透過 STT 文字輸入 Gemini
        # 解決 Gemini Live API 音頻 token 累積導致的延遲遞增（1s → 30s）
        #
        # 官方文件：使用 LiveKit turn detection 時，需要額外的 streaming STT
        # https://docs.livekit.io/agents/models/realtime/plugins/gemini/#turn-detection
        session = AgentSession(
            vad=vad,
            stt=inference.STT(model="deepgram/nova-2", language="zh-TW"),
            turn_handling=TurnHandlingOptions(
                turn_detection=MultilingualModel(),
            ),
            llm=TextInputRealtimeModel(
                model=realtime_model,
                voice=realtime_voice,
                temperature=0.8,
                thinking_config=thinking_cfg,
                input_audio_transcription=None,  # 關閉 Gemini 內部轉寫，改用外部 STT
                realtime_input_config=genai_types.RealtimeInputConfig(
                    automatic_activity_detection=genai_types.AutomaticActivityDetection(
                        disabled=True,
                    ),
                ),
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

    # Event buffer: metric events appended synchronously during the session,
    # chat-history events appended once at shutdown. Flushed to DB inside
    # log_usage() so the whole session write is atomic per DB session.
    events_buffer: list[dict] = []
    event_seq = 0

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        nonlocal last_eou_metrics, event_seq
        if ev.metrics.type == "eou_metrics":
            last_eou_metrics = ev.metrics
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

        if _db_available and db_session_id:
            event_seq += 1
            try:
                payload = (
                    ev.metrics.model_dump(mode="json")
                    if hasattr(ev.metrics, "model_dump")
                    else {"repr": repr(ev.metrics)}
                )
            except Exception:
                payload = {"repr": repr(ev.metrics)}
            events_buffer.append(
                {
                    "seq": event_seq,
                    "event_type": f"metric_{ev.metrics.type}",
                    "payload_json": payload,
                }
            )

    async def log_usage():
        nonlocal event_seq
        summary = usage_collector.get_summary()
        logger.info("Usage summary: %s", summary)

        # ── Write session results to DB ──
        if _db_available and db_session_id:
            try:
                # Flush chat transcript (user/agent messages) from session.history
                for item in getattr(session.history, "items", []):
                    event_seq += 1
                    role = getattr(item, "role", "message")
                    text = getattr(item, "text_content", None)
                    events_buffer.append(
                        {
                            "seq": event_seq,
                            "event_type": f"chat_{role}",
                            "payload_json": {
                                "role": role,
                                "text": text if text is not None else repr(item),
                            },
                        }
                    )

                cost_result = compute_cost(summary)
                # UsageCollector.get_summary() has no "duration" key; compute
                # it from the wall clock so the UI shows real session length.
                started_at = session_started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                duration = (datetime.now(timezone.utc) - started_at).total_seconds()

                factory = get_session_factory()
                with factory() as db:
                    if events_buffer:
                        session_store.add_events(db, db_session_id, events_buffer)
                    session_store.complete_session(
                        db,
                        db_session_id,
                        shutdown_reason="session_end",
                        duration_seconds=duration,
                        total_cost_usd=cost_result.get("total_usd"),
                        raw_report_json={
                            "usage_summary": summary,
                            "cost": cost_result,
                        },
                    )
                logger.info(
                    "DB session completed: %s (events=%d, duration=%.1fs, cost=$%s)",
                    db_session_id,
                    len(events_buffer),
                    duration,
                    cost_result.get("total_usd", "N/A"),
                )
            except Exception:
                logger.exception("Failed to complete DB session %s", db_session_id)

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
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        ),
    )

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="voice-assistant"))
