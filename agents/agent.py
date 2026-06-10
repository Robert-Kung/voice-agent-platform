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
    room_io,
)
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents import metrics, MetricsCollectedEvent, AgentStateChangedEvent

from agent_factory import load_profile_with_id, create_agent_class, list_profiles
from runtime.providers import resolve_session_components

logger = logging.getLogger("agent")


# ── connect-mode JWT fix ───────────────────────────────────
# livekit-agents 1.5.2 Worker.simulate_job() 產的 JWT 沒含 can_update_own_metadata=True，
# 導致 connect-mode agent 無法 set_attributes() → lk.agent.state 永遠傳不到前端
# → useAgent() 20s timeout 後 state='failed' → useAgentErrors 觸發 session.end()
# → CLIENT_INITIATED 斷線。只影響本地 Try button（走 connect subcommand），
# Cloud dispatch 路徑用 server 發的 token 不受影響。
def _patch_connect_mode_token() -> None:
    from livekit import api
    from livekit.agents.worker import AgentServer

    _orig = AgentServer.simulate_job

    async def _patched(
        self,
        room,
        *,
        fake_job=False,
        agent_identity=None,
        room_info=None,
        token=None,
    ):
        if token is None and agent_identity and not fake_job:
            token = (
                api.AccessToken(self._api_key, self._api_secret)
                .with_identity(agent_identity)
                .with_kind("agent")
                .with_grants(
                    api.VideoGrants(
                        room_join=True,
                        room=room,
                        agent=True,
                        can_update_own_metadata=True,
                    )
                )
                .to_jwt()
            )
        return await _orig(
            self,
            room,
            fake_job=fake_job,
            agent_identity=agent_identity,
            room_info=room_info,
            token=token,
        )

    AgentServer.simulate_job = _patched


def _maybe_patch_connect_mode_token() -> None:
    """Apply the connect-mode JWT patch only when this process is running the
    `connect` subcommand. Cloud dispatch (`start`/`dev`) doesn't need it, and
    leaving the patch off those paths avoids touching internal LiveKit APIs in
    production. Also gate on a known-good livekit-agents version range so the
    patch fails loudly on upgrades that change `simulate_job`'s signature
    instead of silently breaking.
    """
    argv = sys.argv[1:]
    if not argv or argv[0] != "connect":
        return

    # The patch was written against livekit-agents 1.5.x — specifically the
    # simulate_job signature in that minor. Allow only that range; future
    # minors (1.6+, 2.x) skip the patch with a warning so a routine upgrade
    # surfaces "Try button stopped working" instead of silently misbehaving.
    _PATCH_MIN = "1.5.0"
    _PATCH_MAX_EXCLUSIVE = "1.6.0"

    try:
        from importlib.metadata import version as _pkg_version
        from packaging.version import Version

        agents_version = Version(_pkg_version("livekit-agents"))
    except Exception:
        # If we can't even read the version (e.g. importlib/packaging broken),
        # treat that as "unknown version" and skip — applying a 1.5.x-shaped
        # patch to an unknown version is exactly the silent-break we're trying
        # to avoid. Try-button breaking loudly is the better failure mode.
        logger.exception("connect-mode patch version check failed; skipping patch")
        return

    if not (Version(_PATCH_MIN) <= agents_version < Version(_PATCH_MAX_EXCLUSIVE)):
        logger.warning(
            "Skipping connect-mode token patch: livekit-agents %s is outside "
            "the validated range [%s, %s). Re-test simulate_job() before "
            "extending this gate.",
            agents_version, _PATCH_MIN, _PATCH_MAX_EXCLUSIVE,
        )
        return

    _patch_connect_mode_token()


_maybe_patch_connect_mode_token()

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
# Moved to runtime/providers.py — the resolver now owns realtime LLM construction
# (model/voice/forced latency settings). Behavior is unchanged; see the class
# docstring there and agent_factory.on_user_turn_completed for the full signal flow:
#   [語音] → Silero VAD → Deepgram STT → MultilingualModel EOU
#         → on_user_turn_completed → session.generate_reply(user_input=text)
#         → Gemini（文字輸入）→ 語音輸出
# ───────────────────────────────────────────────────────────

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
# 控制語音處理架構：
#   "pipeline"  — STT → LLM → TTS 分離式管線（使用 LiveKit Inference）
#   "realtime"  — Gemini Live + 外部 STT 文字輸入（預設，TextInputRealtimeModel）
#
# 優先序（高到低）：
#   1. AGENT_MODE env（明確設定時 override）
#   2. profile config 的 models.mode
#   3. 內建預設 _DEFAULT_MODE
#
# 注意：env 偵測用 `"AGENT_MODE" in os.environ`，不可用 `.get(..., "realtime")`，
# 否則 unset 會塌成 realtime，讓「env 未設 → 用 models.mode」這條路永遠走不到。
# STT provider 選擇（AGENT_STT_PROVIDER / via）已下沉到 runtime/providers.py。
# ───────────────────────────────────────────────────────────
_DEFAULT_MODE = "realtime"


def _resolve_mode(profile: dict) -> str:
    """Effective agent mode: AGENT_MODE env override > profile models.mode > default."""
    if "AGENT_MODE" in os.environ:
        return os.environ["AGENT_MODE"].strip().lower()
    models = (profile or {}).get("models") or {}
    mode = models.get("mode")
    if mode:
        return str(mode).strip().lower()
    return _DEFAULT_MODE


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
logger.info("Mode: AGENT_MODE env=%s, default=%s (per-profile models.mode applies when env unset)",
            os.environ.get("AGENT_MODE", "<unset>"), _DEFAULT_MODE)
logger.info("Available profiles: %s", ", ".join(list_profiles()))


async def entrypoint(ctx: JobContext):
    # ── 動態選擇 profile（支援 room metadata 切換）──
    profile_name = _get_runtime_profile_name(ctx)
    profile, db_profile_id = load_profile_with_id(profile_name)

    # Effective mode is per-profile (models.mode) with AGENT_MODE env override —
    # resolved AFTER the profile loads, then threaded into both the agent class
    # and the session build. No reliance on a module-global read at import time.
    agent_mode = _resolve_mode(profile)
    PhoneAgent = create_agent_class(profile, mode=agent_mode)
    logger.info("Session using profile: %s (%s), mode: %s", profile.get("name"), profile_name, agent_mode)

    # Resolve swappable model components + the selected model names (for cost).
    resolved = resolve_session_components(profile, agent_mode)

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
                    agent_mode=agent_mode,
                    model_names=resolved.model_names,
                )
                db_session_id = db_sess.id
                session_started_at = db_sess.started_at
                logger.info("DB session created: %s (models=%s)", db_session_id, resolved.model_names)
        except Exception:
            logger.exception("Failed to create DB session")

    vad = silero.VAD.load(
        activation_threshold=0.7,    # 預設 0.5；調高減少 SIP echo/雜音誤觸
        min_silence_duration=1.0,    # 預設 0.55s；調長避免 agent 說話停頓被誤判 EOU
        min_speech_duration=0.15,    # 預設 0.05s；過濾短暫雜音
    )

    if agent_mode == "realtime":
        # ── Realtime（Gemini Live + 外部 STT 文字輸入）──
        # LLM 與 STT 元件由 resolver 建好（resolved.llm 是 TextInputRealtimeModel，
        # 強制套用 input_audio_transcription=None + automatic_activity_detection.disabled
        # 等延遲規避設定；resolved.stt 是文字輸入來源）。
        #
        # SIP Echo 解法：關閉 Gemini VAD，改由 LiveKit Silero VAD 控制。
        # turn_detection 必須保持外部 MultilingualModel，確保 SDK 不跳過
        # on_user_turn_completed 回調（SDK 在 turn_detection=True 時會直接 return，
        # 不觸發 agent_factory 的文字轉發流程）。
        # 官方文件：使用 LiveKit turn detection 時，需要額外的 streaming STT
        # https://docs.livekit.io/agents/models/realtime/plugins/gemini/#turn-detection
        session = AgentSession(
            vad=vad,
            stt=resolved.stt,
            turn_handling=TurnHandlingOptions(
                turn_detection=MultilingualModel(),
            ),
            llm=resolved.llm,
        )
    else:
        # ── Pipeline 模式（STT → LLM → TTS，profile-driven via resolver）──
        session = AgentSession(
            llm=resolved.llm,
            stt=resolved.stt,
            tts=resolved.tts,
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
                    item_type = getattr(item, "type", None)

                    if item_type == "function_call":
                        events_buffer.append({
                            "seq": event_seq,
                            "event_type": "function_call",
                            "payload_json": {
                                "name": item.name,
                                "call_id": item.call_id,
                                "arguments": item.arguments,
                            },
                        })
                    elif item_type == "function_call_output":
                        events_buffer.append({
                            "seq": event_seq,
                            "event_type": "function_call_output",
                            "payload_json": {
                                "name": item.name,
                                "call_id": item.call_id,
                                "output": item.output,
                                "is_error": item.is_error,
                            },
                        })
                    else:
                        role = getattr(item, "role", "message")
                        text = getattr(item, "text_content", None)
                        events_buffer.append({
                            "seq": event_seq,
                            "event_type": f"chat_{role}",
                            "payload_json": {
                                "role": role,
                                "text": text if text is not None else repr(item),
                            },
                        })

                cost_result = compute_cost(
                    summary, agent_mode=agent_mode, selected=resolved.model_names
                )
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
                            "usage_summary": (
                                summary if isinstance(summary, dict)
                                else {k: getattr(summary, k, None) for k in summary.__dataclass_fields__}
                                if hasattr(summary, "__dataclass_fields__")
                                else str(summary)
                            ),
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

    try:
        await session.start(
            agent=PhoneAgent(),
            room=ctx.room,
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(
                    noise_cancellation=noise_cancellation.BVC(),
                ),
            ),
        )
    except Exception:
        logger.exception(
            "session.start() failed — profile=%s mode=%s room=%s",
            profile_name, agent_mode,
            ctx.room.name if ctx.room else "None",
        )
        raise

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="voice-assistant"))
