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
    """Fuzzy-match a model/provider name against rate table keys.

    Longer keys are checked first so that specific names (e.g. "gpt-4o-mini")
    win over their substrings ("gpt-4o"). Without this ordering, the first
    registered key wins and more-specific rates get silently skipped.
    """
    key_lower = key.lower()
    for k in sorted(rate_table, key=len, reverse=True):
        if k.lower() in key_lower:
            return rate_table[k]
    return None


def _match_llm_rate(llm_model: str) -> dict[str, float] | None:
    """Match the longest registered LLM key that is a substring of llm_model.

    Dict iteration order is insertion-order, so naive `for k in LLM_RATES`
    caused `google/gemini-2.5-flash-lite` to match `google/gemini-2.5-flash`
    first and pay the wrong rate. Sorting by length reverse-first fixes this.
    """
    model_lower = llm_model.lower()
    for model_key in sorted(LLM_RATES, key=len, reverse=True):
        if model_key.lower() in model_lower:
            return LLM_RATES[model_key]
    return None


def compute_cost(usage_summary) -> dict:
    """Compute cost from a UsageCollector summary (dict or UsageSummary object).

    Args:
        usage_summary: dict or livekit.agents.metrics.UsageSummary with fields
                       like 'llm_prompt_tokens', 'llm_completion_tokens',
                       'tts_characters_count', 'stt_audio_duration', etc.

    Returns:
        {
            "llm_usd": float | None,
            "tts_usd": float | None,
            "stt_usd": float | None,
            "total_usd": float | None,
            "incomplete": bool,
        }
    """
    # Normalise: accept both plain dict and UsageSummary dataclass/object
    if isinstance(usage_summary, dict):
        def _get(key: str, default=0):
            return usage_summary.get(key, default)
    else:
        def _get(key: str, default=0):
            return getattr(usage_summary, key, default) or default

    llm_usd = None
    tts_usd = None
    stt_usd = None
    incomplete = False

    # LLM cost
    prompt_tokens = _get("llm_prompt_tokens", 0)
    completion_tokens = _get("llm_completion_tokens", 0)
    llm_model = _get("llm_model", "")
    if prompt_tokens or completion_tokens:
        rate = _match_llm_rate(llm_model)
        if rate:
            llm_usd = (prompt_tokens * rate["in"] + completion_tokens * rate["out"]) / 1_000_000
        else:
            incomplete = True

    # TTS cost — estimate from characters (rough: 150 chars ≈ 1 minute for zh)
    tts_chars = _get("tts_characters_count", 0) or _get("tts_characters", 0)
    tts_provider = _get("tts_model", "")
    if tts_chars:
        rate = _match_rate(tts_provider, TTS_RATES)
        if rate:
            estimated_minutes = tts_chars / 150.0
            tts_usd = estimated_minutes * rate
        else:
            incomplete = True

    # STT cost — from audio duration in seconds
    stt_duration = _get("stt_audio_duration", 0)
    stt_provider = _get("stt_model", "")
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
