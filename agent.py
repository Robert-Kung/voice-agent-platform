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
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents import metrics, MetricsCollectedEvent, AgentStateChangedEvent

from agent_factory import load_profile, create_agent_class, list_profiles

logger = logging.getLogger("agent")

load_dotenv(".env")

# ── Profile 選擇 ──────────────────────────────────────────
# 透過環境變數 AGENT_PROFILE 或命令列 --profile / -p 指定
# 預設使用 car_inspection
#
# 用法：
#   uv run agent.py console --profile restaurant
#   uv run agent.py console -p dental_clinic
#   AGENT_PROFILE=restaurant uv run agent.py console
# ───────────────────────────────────────────────────────────

def _get_profile_name() -> str:
    """從 sys.argv 或環境變數取得 profile 名稱。"""
    # 先檢查命令列參數 --profile / -p
    for i, arg in enumerate(sys.argv):
        if arg in ("--profile", "-p") and i + 1 < len(sys.argv):
            name = sys.argv.pop(i + 1)
            sys.argv.pop(i)
            return name

    # 再檢查環境變數
    return os.environ.get("AGENT_PROFILE", "car_inspection")


PROFILE_NAME = _get_profile_name()

try:
    PROFILE = load_profile(PROFILE_NAME)
except FileNotFoundError as e:
    logger.error(str(e))
    sys.exit(1)

PhoneAgent = create_agent_class(PROFILE)
AGENT_NAME = PROFILE.get("agent_name", "voice-assistant")

logger.info("Loaded profile: %s (%s)", PROFILE.get("name"), PROFILE_NAME)
logger.info("Available profiles: %s", ", ".join(list_profiles()))


async def entrypoint(ctx: JobContext):
    vad = silero.VAD.load()

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
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name=AGENT_NAME))
