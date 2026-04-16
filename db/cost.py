"""Cost estimation — derive USD from session metrics_collected data."""

from __future__ import annotations

# USD per 1M tokens (input / output)
LLM_RATES: dict[str, dict[str, float]] = {
    # Google
    "google/gemini-2.5-flash": {"in": 0.15, "out": 0.60},
    "google/gemini-2.5-flash-lite": {"in": 0.075, "out": 0.30},
    "google/gemini-3.1-flash-lite": {"in": 0.075, "out": 0.30},
    "google/gemini-2.0-flash": {"in": 0.10, "out": 0.40},
    # OpenAI
    "openai/gpt-4o-mini": {"in": 0.15, "out": 0.60},
    "openai/gpt-4.1-mini": {"in": 0.40, "out": 1.60},
    "openai/gpt-4o": {"in": 2.50, "out": 10.00},
    "openai/gpt-4.1": {"in": 2.00, "out": 8.00},
}

# USD per minute of audio
TTS_RATES: dict[str, float] = {
    "cartesia": 0.020,
    "elevenlabs": 0.018,
    "openai": 0.015,
    "google": 0.016,
}

# USD per minute of audio
STT_RATES: dict[str, float] = {
    "deepgram": 0.0043,
    "elevenlabs": 0.010,
    "google": 0.006,
}


def _match_rate(key: str, rate_table: dict[str, float]) -> float | None:
    """Fuzzy-match a model/provider name against rate table keys."""
    key_lower = key.lower()
    for k, v in rate_table.items():
        if k.lower() in key_lower:
            return v
    return None


def compute_cost(usage_summary: dict) -> dict:
    """Compute cost from a UsageCollector summary dict.

    Args:
        usage_summary: dict with keys like 'llm_prompt_tokens', 'llm_completion_tokens',
                       'tts_characters', 'stt_audio_duration', etc.

    Returns:
        {
            "llm_usd": float | None,
            "tts_usd": float | None,
            "stt_usd": float | None,
            "total_usd": float | None,
            "incomplete": bool,
        }
    """
    llm_usd = None
    tts_usd = None
    stt_usd = None
    incomplete = False

    # LLM cost
    prompt_tokens = usage_summary.get("llm_prompt_tokens", 0)
    completion_tokens = usage_summary.get("llm_completion_tokens", 0)
    llm_model = usage_summary.get("llm_model", "")
    if prompt_tokens or completion_tokens:
        rate = None
        for model_key, rates in LLM_RATES.items():
            if model_key.lower() in llm_model.lower():
                rate = rates
                break
        if rate:
            llm_usd = (prompt_tokens * rate["in"] + completion_tokens * rate["out"]) / 1_000_000
        else:
            incomplete = True

    # TTS cost — estimate from characters (rough: 150 chars ≈ 1 minute for zh)
    tts_chars = usage_summary.get("tts_characters", 0)
    tts_provider = usage_summary.get("tts_model", "")
    if tts_chars:
        rate = _match_rate(tts_provider, TTS_RATES)
        if rate:
            estimated_minutes = tts_chars / 150.0
            tts_usd = estimated_minutes * rate
        else:
            incomplete = True

    # STT cost — from audio duration in seconds
    stt_duration = usage_summary.get("stt_audio_duration", 0)
    stt_provider = usage_summary.get("stt_model", "")
    if stt_duration:
        rate = _match_rate(stt_provider, STT_RATES)
        if rate:
            stt_usd = (stt_duration / 60.0) * rate
        else:
            incomplete = True

    # Total
    parts = [x for x in [llm_usd, tts_usd, stt_usd] if x is not None]
    total_usd = sum(parts) if parts else None

    return {
        "llm_usd": llm_usd,
        "tts_usd": tts_usd,
        "stt_usd": stt_usd,
        "total_usd": total_usd,
        "incomplete": incomplete,
    }
