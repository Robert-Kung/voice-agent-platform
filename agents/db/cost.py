"""Cost estimation — derive USD from session metrics_collected data.

Two modes:
  - "pipeline": separate STT + LLM + TTS plugins; cost = LLM tokens + STT minutes + TTS minutes.
  - "realtime": one streaming model (e.g. Gemini Live native audio) with mixed
    audio + text token billing; cost = audio_in × audio_in_rate + audio_out × audio_out_rate
    + text_in × text_in_rate + text_out × text_out_rate.
"""

from __future__ import annotations

# ── Realtime: per-1M token rates for streaming/native-audio models ─────────
# Source: Google Gemini Live API pricing (2.5 Flash native audio preview).
# Update these alongside model changes.
REALTIME_RATES: dict[str, dict[str, float]] = {
    # Keyed so the key is a SUBSTRING of the actual model name the resolver records
    # (e.g. "gemini-2.5-flash-native-audio-preview-12-2025"), so _match_realtime_rate
    # resolves the selected variant to its own rate instead of silently falling to
    # the default. Adding a realtime variant to REALTIME_MODEL_ALLOWLIST requires a
    # matching key here (code-review fix).
    "gemini-2.5-flash-native-audio": {
        "audio_in": 3.00,
        "audio_out": 12.00,
        "text_in": 0.50,
        "text_out": 2.00,
        "cached_in": 0.075,
    },
}

# Default realtime rate to use when the selected variant isn't in the table.
_REALTIME_DEFAULT = "gemini-2.5-flash-native-audio"


# ── Pipeline: per-1M tokens (LLM) / per-minute (audio) ────────────────────
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
    win over their substrings ("gpt-4o").
    """
    key_lower = key.lower()
    for k in sorted(rate_table, key=len, reverse=True):
        if k.lower() in key_lower:
            return rate_table[k]
    return None


def _match_llm_rate(llm_model: str) -> dict[str, float] | None:
    model_lower = (llm_model or "").lower()
    for model_key in sorted(LLM_RATES, key=len, reverse=True):
        if model_key.lower() in model_lower:
            return LLM_RATES[model_key]
    return None


def _match_realtime_rate(name: str | None) -> tuple[dict[str, float], str]:
    """Pick a realtime rate by the selected Gemini Live variant, falling back to
    the default when the variant isn't in the table (D5). Returns (rate, key)."""
    if name:
        name_lower = name.lower()
        for key in sorted(REALTIME_RATES, key=len, reverse=True):
            if key.lower() in name_lower or name_lower in key.lower():
                return REALTIME_RATES[key], key
    return REALTIME_RATES[_REALTIME_DEFAULT], _REALTIME_DEFAULT


def _is_realtime(usage_summary, agent_mode: str | None) -> bool:
    """Heuristic: explicit agent_mode wins; else fall back to audio-token
    presence which only realtime / native-audio models produce."""
    if agent_mode == "realtime":
        return True
    if agent_mode == "pipeline":
        return False
    if isinstance(usage_summary, dict):
        return bool(usage_summary.get("llm_input_audio_tokens") or usage_summary.get("llm_output_audio_tokens"))
    return bool(getattr(usage_summary, "llm_input_audio_tokens", 0) or getattr(usage_summary, "llm_output_audio_tokens", 0))


def _compute_realtime_cost(get, selected: dict | None = None) -> dict:
    """Compute cost for a realtime streaming model using granular token fields.

    `selected` carries the resolver's chosen model names (realtime_model /
    realtime_stt) recorded on the session row, so rates are driven by the actual
    selection rather than guessed.
    """
    selected = selected or {}
    rate, model_key = _match_realtime_rate(selected.get("realtime_model"))

    audio_in = get("llm_input_audio_tokens", 0)
    audio_in_cached = get("llm_input_cached_audio_tokens", 0)
    text_in = get("llm_input_text_tokens", 0)
    text_in_cached = get("llm_input_cached_text_tokens", 0)
    audio_out = get("llm_output_audio_tokens", 0)
    text_out = get("llm_output_text_tokens", 0)

    audio_in_billable = max(audio_in - audio_in_cached, 0)
    text_in_billable = max(text_in - text_in_cached, 0)
    cached_total = audio_in_cached + text_in_cached

    llm_usd = (
        audio_in_billable * rate["audio_in"]
        + audio_out * rate["audio_out"]
        + text_in_billable * rate["text_in"]
        + text_out * rate["text_out"]
        + cached_total * rate["cached_in"]
    ) / 1_000_000

    # STT is part of the realtime path — text-input architecture routes audio
    # through STT first, then forwards transcript to Gemini Live. Rate is driven by
    # the selected realtime STT provider via the shared STT_RATES table (single
    # source of truth — no separate hard-coded constant). Defaults to deepgram,
    # which the realtime architecture always uses.
    stt_name = selected.get("realtime_stt") or "deepgram/nova-2"
    stt_rate_per_min = _match_rate(stt_name, STT_RATES) or STT_RATES["deepgram"]
    stt_seconds = get("stt_audio_duration", 0)
    stt_usd = (stt_seconds / 60.0) * stt_rate_per_min if stt_seconds > 0 else None

    parts = [x for x in [llm_usd, stt_usd] if x is not None]
    total_usd = sum(parts) if parts else None

    return {
        "mode": "realtime",
        "model": model_key,
        "stt_provider": stt_name if stt_usd is not None else None,
        "rates_per_1m": rate,
        "stt_rate_per_min": stt_rate_per_min,
        "tokens": {
            "audio_in": audio_in,
            "audio_in_cached": audio_in_cached,
            "audio_out": audio_out,
            "text_in": text_in,
            "text_in_cached": text_in_cached,
            "text_out": text_out,
        },
        "stt_audio_seconds": stt_seconds,
        "llm_usd": llm_usd,
        "tts_usd": None,
        "stt_usd": stt_usd,
        "total_usd": total_usd,
        "incomplete": False,
    }


def _compute_pipeline_cost(get, selected: dict | None = None) -> dict:
    """Compute cost for the STT + LLM + TTS pipeline.

    Model names come from `selected` (the resolver's choice, recorded on the
    session row) when available; otherwise fall back to the metrics-reported
    name. This matters because once a fallback chain is used, the metrics
    `*_model` is the literal "FallbackAdapter" (see fallback_adapter.py:80), which
    no rate key matches — so without `selected` every chained session would be
    marked incomplete.
    """
    selected = selected or {}
    llm_usd = None
    tts_usd = None
    stt_usd = None
    incomplete = False

    prompt_tokens = get("llm_prompt_tokens", 0)
    completion_tokens = get("llm_completion_tokens", 0)
    llm_model = selected.get("llm") or get("llm_model", "")
    if prompt_tokens or completion_tokens:
        rate = _match_llm_rate(llm_model)
        if rate:
            llm_usd = (prompt_tokens * rate["in"] + completion_tokens * rate["out"]) / 1_000_000
        else:
            incomplete = True

    tts_chars = get("tts_characters_count", 0) or get("tts_characters", 0)
    tts_provider = selected.get("tts") or get("tts_model", "")
    if tts_chars:
        rate = _match_rate(tts_provider, TTS_RATES)
        if rate:
            estimated_minutes = tts_chars / 150.0
            tts_usd = estimated_minutes * rate
        else:
            incomplete = True

    stt_duration = get("stt_audio_duration", 0)
    stt_provider = selected.get("stt") or get("stt_model", "")
    if stt_duration:
        rate = _match_rate(stt_provider, STT_RATES)
        if rate:
            stt_usd = (stt_duration / 60.0) * rate
        else:
            incomplete = True

    parts = [x for x in [llm_usd, tts_usd, stt_usd] if x is not None]
    total_usd = sum(parts) if parts else None

    return {
        "mode": "pipeline",
        "llm_usd": llm_usd,
        "tts_usd": tts_usd,
        "stt_usd": stt_usd,
        "total_usd": total_usd,
        "incomplete": incomplete,
    }


def compute_cost(usage_summary, agent_mode: str | None = None, selected: dict | None = None) -> dict:
    """Compute cost from a UsageCollector summary.

    Args:
        usage_summary: dict or UsageSummary with token / audio fields.
        agent_mode: "realtime" / "pipeline" / None — when None, auto-detect
                    from the presence of audio tokens.
        selected: resolver-selected model names recorded on the session row
                  (e.g. {"llm": "google/gemini-3.1-flash-lite"} or
                  {"realtime_model": "...", "realtime_stt": "deepgram/nova-2"}).
                  Preferred over the metrics-reported model name, which is the
                  literal "FallbackAdapter" for any fallback chain.

    Returns:
        Realtime: {mode, model, rates_per_1m, tokens, llm_usd, total_usd, incomplete=False, ...}
        Pipeline: {mode, llm_usd, tts_usd, stt_usd, total_usd, incomplete}
    """
    if isinstance(usage_summary, dict):
        def get(key: str, default=0):
            return usage_summary.get(key, default) or default
    else:
        def get(key: str, default=0):
            return getattr(usage_summary, key, default) or default

    if _is_realtime(usage_summary, agent_mode):
        return _compute_realtime_cost(get, selected)
    return _compute_pipeline_cost(get, selected)
