"""Resolve declarative model specs into concrete LiveKit components.

Lighter design (plan-eng-review decision): `via: inference` is a gateway
passthrough (`inference.LLM/STT/TTS("{provider}/{model}")`); `via: direct`
special-cases only the in-use direct providers (deepgram STT, google realtime).
Any other direct combo fails loud. The full (kind, provider, via) registry is
deferred to graph-agent-builder/OQ4 — `build_*` signatures won't change when it
lands, so that upgrade is an internal refactor.

    spec ──normalize──▶ build_one ──▶ component
    [spec, ...] ──build_*──▶ single = bare component | many = FallbackAdapter

Realtime mode is special: the LLM is always a TextInputRealtimeModel wrapping
Gemini Live (latency mitigation, design D3), built here with forced settings the
profile cannot override.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from livekit.agents import inference, llm, stt, tts
from livekit.plugins import deepgram, google
from google.genai import types as genai_types

from runtime.constants import (
    REALTIME_LLM_PROVIDERS,
    REALTIME_MODEL_ALLOWLIST,
    SpecError,
    VIA_DIRECT,
    VIA_INFERENCE,
    normalize_spec,
    normalize_specs,
)

logger = logging.getLogger("runtime.providers")


# ── TextInputRealtimeModel ─────────────────────────────────
# Moved here from agent.py so the resolver owns realtime LLM construction.
# Solves Gemini Live audio-token accumulation latency: intercept push_audio /
# start_user_activity (no-op) and feed transcript text from external STT instead
# of raw audio. Full signal flow documented in agent_factory.on_user_turn_completed.
class TextInputRealtimeModel(google.realtime.RealtimeModel):
    """RealtimeModel wrapper that intercepts audio push → pure text-input mode."""

    def session(self):
        sess = super().session()
        sess.push_audio = lambda frame: None
        sess.start_user_activity = lambda: None
        return sess


# ── Built-in defaults (backfill) ───────────────────────────
# Expressed as specs and run through the same build path, so a profile WITHOUT a
# models block produces a session byte-for-byte identical to the pre-change
# hard-coded lists (regression test 5.4). The deepgram STT spec stays via:inference
# here; AGENT_STT_PROVIDER=deepgram flips it to direct per-spec (see _apply_stt_override).
_DEFAULT_PIPELINE_LLM = [
    {"provider": "google", "model": "gemini-3.1-flash-lite", "via": VIA_INFERENCE},
    {"provider": "openai", "model": "gpt-4.1-mini", "via": VIA_INFERENCE},
]
_DEFAULT_PIPELINE_STT = [
    {"provider": "elevenlabs", "model": "scribe_v2_realtime", "via": VIA_INFERENCE, "language": "zh"},
    {"provider": "deepgram", "model": "nova-2", "via": VIA_INFERENCE, "language": "zh-TW"},
]
_DEFAULT_PIPELINE_TTS = [
    {"provider": "cartesia", "model": "sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc", "via": VIA_INFERENCE, "language": "zh"},
    {"provider": "elevenlabs", "model": "eleven_multilingual_v2", "via": VIA_INFERENCE, "language": "zh"},
]
_DEFAULT_REALTIME_STT = {"provider": "deepgram", "model": "nova-2", "via": VIA_INFERENCE, "language": "zh-TW"}


def _model_id(spec: dict) -> str:
    """Canonical `provider/model` string — matches the cost rate-table key format."""
    return f"{spec['provider']}/{spec['model']}"


# ── AGENT_STT_PROVIDER global override ─────────────────────
def _apply_stt_override(spec: dict) -> dict:
    """Legacy AGENT_STT_PROVIDER env override: when set to "deepgram", force a
    deepgram STT spec to via:direct (Try button dodging the free-plan Inference STT
    concurrency quota). Higher precedence than the spec's own `via` (design D2).

    Only "deepgram" is honored — it's the sole direct-buildable STT provider.
    Any other value (incl. "inference" or a typo) is a no-op, mirroring the legacy
    `_build_stt`, which defaulted everything-but-deepgram to inference. Flipping a
    non-deepgram provider to direct would crash session start with no fallback net.
    """
    override = os.environ.get("AGENT_STT_PROVIDER", "").strip().lower()
    if override == "deepgram" and spec["provider"] == "deepgram":
        return {**spec, "via": VIA_DIRECT}
    return spec


# ── Component builders ─────────────────────────────────────
def _build_one_llm(spec: dict):
    if spec["via"] == VIA_INFERENCE:
        return inference.LLM(model=_model_id(spec), **spec["options"])
    raise SpecError(
        f"direct LLM provider '{spec['provider']}' not supported; use via:inference "
        f"(direct is only wired for deepgram STT and google realtime)"
    )


def _build_one_stt(spec: dict):
    spec = _apply_stt_override(spec)
    language = spec.get("language") or "zh-TW"
    if spec["via"] == VIA_DIRECT:
        if spec["provider"] == "deepgram":
            return deepgram.STT(model=spec["model"], language=language, **spec["options"])
        raise SpecError(f"direct STT provider '{spec['provider']}' not supported; use via:inference")
    return inference.STT(model=_model_id(spec), language=language, **spec["options"])


def _build_one_tts(spec: dict):
    language = spec.get("language") or "zh"
    if spec["via"] == VIA_DIRECT:
        raise SpecError(f"direct TTS provider '{spec['provider']}' not supported; use via:inference")
    return inference.TTS(model=_model_id(spec), language=language, **spec["options"])


def build_llm(specs: list[dict]):
    comps = [_build_one_llm(s) for s in specs]
    if not comps:
        return None
    return comps[0] if len(comps) == 1 else llm.FallbackAdapter(comps)


def build_stt(specs: list[dict]):
    comps = [_build_one_stt(s) for s in specs]
    if not comps:
        return None
    return comps[0] if len(comps) == 1 else stt.FallbackAdapter(comps)


def build_tts(specs: list[dict]):
    comps = [_build_one_tts(s) for s in specs]
    if not comps:
        return None
    return comps[0] if len(comps) == 1 else tts.FallbackAdapter(comps)


# ── Realtime LLM ───────────────────────────────────────────
def build_realtime_llm(realtime: dict):
    """Build the TextInputRealtimeModel from a `models.realtime` block, forcing the
    latency-mitigation settings the profile cannot override (design D3). Falls back
    to the existing env-driven defaults for missing fields. Rejects non-Gemini
    providers (fail loud)."""
    realtime = realtime or {}

    provider = realtime.get("provider")
    if provider and str(provider).strip().lower() not in REALTIME_LLM_PROVIDERS:
        raise SpecError(
            f"realtime LLM provider '{provider}' not supported — realtime is locked "
            f"to Gemini Live (TextInputRealtimeModel)."
        )

    model = realtime.get("model") or os.environ.get(
        "GOOGLE_REALTIME_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025"
    )
    if model not in REALTIME_MODEL_ALLOWLIST:
        # Don't hard-fail the env escape hatch, but make a bad profile-pinned
        # variant loud — realtime has no fallback net.
        logger.warning(
            "Realtime model '%s' is not in the supported allowlist %s; "
            "proceeding but this variant may 1007 mid-session.",
            model, sorted(REALTIME_MODEL_ALLOWLIST),
        )
    voice = realtime.get("voice") or os.environ.get("GOOGLE_REALTIME_VOICE", "Kore")
    thinking_budget = realtime.get("thinking_budget", 0)

    logger.info("Realtime mode: model=%s, voice=%s, thinking_budget=%s", model, voice, thinking_budget)

    realtime_llm = TextInputRealtimeModel(
        model=model,
        voice=voice,
        temperature=0.8,
        thinking_config=genai_types.ThinkingConfig(thinkingBudget=thinking_budget),
        # Forced latency-mitigation settings — NOT overridable by profile.
        input_audio_transcription=None,
        realtime_input_config=genai_types.RealtimeInputConfig(
            automatic_activity_detection=genai_types.AutomaticActivityDetection(
                disabled=True,
            ),
        ),
    )
    return realtime_llm, model, voice


# ── Resolver ───────────────────────────────────────────────
@dataclass
class ResolvedComponents:
    """Built session components + the resolved primary model names for cost.

    agent.py assembles the AgentSession (mode-specific turn handling / VAD live
    there); the resolver only builds the swappable components and reports which
    models it picked, so cost can price by the actual selection instead of the
    metrics-reported name (which is "FallbackAdapter" for any chain — see D5).
    """

    mode: str
    llm: Any
    stt: Any
    tts: Any | None = None
    realtime_voice: str | None = None
    model_names: dict[str, str | None] = field(default_factory=dict)


def resolve_session_components(profile: dict, mode: str, env=None) -> ResolvedComponents:
    """Resolve a profile's `models` block into session components for the given mode.

    Missing specs backfill to the built-in defaults, so a profile without a models
    block is identical to pre-change behavior. Returns the resolved primary model
    names for the cost layer.
    """
    models = (profile or {}).get("models") or {}

    if mode == "realtime":
        realtime_block = models.get("realtime") or {}
        realtime_llm, rt_model, rt_voice = build_realtime_llm(realtime_block)

        stt_spec = normalize_spec("stt", realtime_block.get("stt") or _DEFAULT_REALTIME_STT)
        realtime_stt = build_stt([stt_spec])
        stt_built = _apply_stt_override(stt_spec)

        return ResolvedComponents(
            mode="realtime",
            llm=realtime_llm,
            stt=realtime_stt,
            tts=None,
            realtime_voice=rt_voice,
            model_names={
                "realtime_model": rt_model,
                "realtime_stt": _model_id(stt_built),
            },
        )

    # ── pipeline ──
    llm_specs = normalize_specs("llm", models.get("llm")) or normalize_specs("llm", _DEFAULT_PIPELINE_LLM)
    stt_specs = normalize_specs("stt", models.get("stt")) or normalize_specs("stt", _DEFAULT_PIPELINE_STT)
    tts_specs = normalize_specs("tts", models.get("tts")) or normalize_specs("tts", _DEFAULT_PIPELINE_TTS)

    return ResolvedComponents(
        mode="pipeline",
        llm=build_llm(llm_specs),
        stt=build_stt(stt_specs),
        tts=build_tts(tts_specs),
        model_names={
            "llm": _model_id(llm_specs[0]) if llm_specs else None,
            "stt": _model_id(stt_specs[0]) if stt_specs else None,
            "tts": _model_id(tts_specs[0]) if tts_specs else None,
        },
    )
