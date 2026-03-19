import logging

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
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
from livekit.plugins import deepgram, noise_cancellation, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents import metrics, MetricsCollectedEvent, AgentStateChangedEvent
from livekit.agents.llm import function_tool
from livekit.agents import RunContext
from livekit.agents import mcp, AgentTask
import httpx
import time



logger = logging.getLogger("agent")

load_dotenv(".env.local")


class CollectConsent(AgentTask[bool]):
    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="""
            詢問使用者是否同意錄音。聆聽明確的「同意」或「不同意」後，呼叫對應工具。
            回答簡短，不超過三句話。
            """,
            chat_ctx=chat_ctx,
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="簡短自我介紹，詢問是否同意錄音以供品質改善使用，並說明可以拒絕。三句話以內。"
        )

    @function_tool
    async def consent_given(self) -> None:
        """Use this when the user gives consent to record."""
        self.complete(True)

    @function_tool
    async def consent_denied(self) -> None:
        """Use this when the user denies consent to record."""
        self.complete(False)


class Manager(Agent):
    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="""
            你是資深客服主管，專業、沉穩、簡潔。
            每次回覆不超過三句話，直接切入重點協助使用者解決問題。
            """,
            tts=inference.TTS(model="cartesia/sonic-3:a167e0f3-df7e-4d52-a9c3-f949145efdab", language="zh"),
            chat_ctx=chat_ctx,
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions="向使用者自我介紹為主管，詢問有什麼可以協助的。兩句話以內。"
        )


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
            你是親切的繁體中文客服助理。
            用簡潔口語回答，每次不超過三句話。
            可查詢天氣，使用英文地名來查詢，也可回答 LiveKit 技術問題（優先查閱文件）。
            需要時可轉接主管。
            """,
        )

    async def on_enter(self) -> None:
        if await CollectConsent(chat_ctx=self.chat_ctx):
            logger.info("User gave consent to record.")
            await self.session.generate_reply(
                instructions="感謝使用者同意錄音，再簡短詢問有什麼可以幫忙的。兩句話以內。"
            )
        else:
            logger.info("User did not give consent to record.")
            await self.session.generate_reply(
                instructions="告知不會錄音，並簡短詢問有什麼可以幫忙的。兩句話以內。"
            )

    @function_tool
    async def escalate_to_manager(self, context: RunContext):
        """Use this tool to escalate the call to the manager, upon user request."""
        return Manager(chat_ctx=self.chat_ctx), "正在為您轉接主管，請稍候。"

    @function_tool
    async def lookup_weather(self, context: RunContext, location: str):
        """Use this tool to look up current weather information in the given location.

        If the location is not supported by the weather service, the tool will indicate this. You must tell the user the location's weather is unavailable.

        Args:
            location: The location to look up weather information for (e.g. city name)
        """

        # WMO weather code descriptions
        WMO_CODES = {
            0: "晴天", 1: "大致晴朗", 2: "部分多雲", 3: "陰天",
            45: "霧", 48: "霧淞",
            51: "毛毛雨（小）", 53: "毛毛雨（中）", 55: "毛毛雨（大）",
            61: "小雨", 63: "中雨", 65: "大雨",
            71: "小雪", 73: "中雪", 75: "大雪",
            80: "陣雨（小）", 81: "陣雨（中）", 82: "陣雨（大）",
            95: "雷陣雨", 96: "雷陣雨伴冰雹", 99: "強雷陣雨伴冰雹",
        }

        logger.info(f"Looking up weather for {location}")

        try:
            await context.session.say(f"正在查詢「{location}」的天氣資訊...")
            context.disallow_interruptions()

            async with httpx.AsyncClient() as client:
                # Step 1: geocoding
                geo_resp = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": location, "count": 1, "language": "zh", "format": "json"},
                    timeout=10,
                )
                geo_data = geo_resp.json().get("results")
                if not geo_data:
                    return f"找不到「{location}」的地理資訊，無法查詢天氣。"

                lat = geo_data[0]["latitude"]
                lon = geo_data[0]["longitude"]
                place_name = geo_data[0].get("name", location)

                # Step 2: current weather
                weather_resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "temperature_2m,weathercode",
                        "temperature_unit": "celsius",
                        "timezone": "auto",
                    },
                    timeout=10,
                )
                current = weather_resp.json().get("current", {})
                temperature = current.get("temperature_2m", "unknown")
                code = current.get("weathercode", -1)
                condition = WMO_CODES.get(code, "未知天氣狀況")

                return f"{place_name}目前天氣：{condition}，氣溫 {temperature}°C"
        except Exception as e:
            logger.error(f"Error fetching weather: {e}")
            return "天氣服務暫時無法使用，請稍後再試。"


async def entrypoint(ctx: JobContext):
    vad = silero.VAD.load()

    session = AgentSession(
        llm=llm.FallbackAdapter(
            [
                inference.LLM(model="openai/gpt-4.1-mini"),
                inference.LLM(model="google/gemini-2.5-flash"),
            ]
        ),
        stt=stt.FallbackAdapter(
            [
                inference.STT(model="deepgram/nova-2", language="zh-TW"),
                inference.STT(model="cartesia/ink-whisper", language="zh"),
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
        mcp_servers=[
            mcp.MCPServerHTTP(
                url="https://docs.livekit.io/mcp/",
                transport_type="streamable_http",
                timeout=30,
            ),
        ],
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

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
