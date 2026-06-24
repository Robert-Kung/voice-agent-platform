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
    DEFAULT_PIPELINE_LLM,
    DEFAULT_PIPELINE_STT,
    DEFAULT_PIPELINE_TTS,
    DEFAULT_REALTIME_MODEL,
    DEFAULT_REALTIME_STT,
    DEFAULT_REALTIME_VOICE,
    REALTIME_LLM_PROVIDERS,
    REALTIME_MODEL_ALLOWLIST,
    SpecError,
    VIA_DIRECT,
    VIA_INFERENCE,
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
# Default specs now live in runtime.constants (import-light, single source shared
# with the model-defaults endpoint). Local aliases keep the call sites below
# unchanged; they're expressed as specs and run through the same build path, so a
# profile WITHOUT a models block produces a session byte-for-byte identical to the
# pre-change behavior (regression: tests/test_runtime_providers.py). The deepgram
# STT spec stays via:inference here; AGENT_STT_PROVIDER=deepgram flips it to direct
# per-spec (see _apply_stt_override).
_DEFAULT_PIPELINE_LLM = DEFAULT_PIPELINE_LLM
_DEFAULT_PIPELINE_STT = DEFAULT_PIPELINE_STT
_DEFAULT_PIPELINE_TTS = DEFAULT_PIPELINE_TTS
_DEFAULT_REALTIME_STT = DEFAULT_REALTIME_STT


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
    # Direct SDK path. google.LLM takes a BARE model name (no provider prefix),
    # unlike inference.LLM which takes "{provider}/{model}". model_names still
    # records the canonical provider/model form (see resolve_session_components)
    # so cost matching is unaffected by via. Key comes from GOOGLE_API_KEY env.
    if spec["via"] == VIA_DIRECT and spec["provider"] == "google":
        return google.LLM(model=spec["model"], **spec["options"])
    raise SpecError(
        f"direct LLM provider '{spec['provider']}' not supported; use via:inference "
        f"(direct LLM is wired only for google)"
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
    # models.tts.voice is a first-class param (LiveKit Inference TTS contract:
    # model + separate voice). Pass it through when present; absent → model-id-only
    # behavior (a voice encoded in the model id, the documented form, still works).
    voice = spec.get("voice")
    kwargs = dict(spec["options"])
    if voice:
        kwargs["voice"] = voice
    return inference.TTS(model=_model_id(spec), language=language, **kwargs)


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
        "GOOGLE_REALTIME_MODEL", DEFAULT_REALTIME_MODEL
    )
    if model not in REALTIME_MODEL_ALLOWLIST:
        # Don't hard-fail the env escape hatch, but make a bad profile-pinned
        # variant loud — realtime has no fallback net.
        logger.warning(
            "Realtime model '%s' is not in the supported allowlist %s; "
            "proceeding but this variant may 1007 mid-session.",
            model, sorted(REALTIME_MODEL_ALLOWLIST),
        )
    voice = realtime.get("voice") or os.environ.get("GOOGLE_REALTIME_VOICE", DEFAULT_REALTIME_VOICE)
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


def _segments(*names: str | None) -> list[dict]:
    """Model-name segments for ResolvedComponents.model_names (one per name)."""
    return [{"model": n} for n in names if n]


def _build_with_preflight(kind: str, raw_specs, default_specs, builder):
    """Normalize + build a component; on a malformed pinned spec OR a build failure,
    degrade to the built-in default chain with a loud warning instead of crashing
    session start.

    A single pinned spec has no FallbackAdapter net, so on a SIP call a stale/
    unbuildable/malformed pin would otherwise drop the call (design D2). NORMALIZATION
    happens inside here so a malformed pin (e.g. a voice-only TTS block with no
    provider/model that the editor can persist — review #1) degrades rather than
    raising SpecError uncaught. This also catches build-time failures (e.g.
    google-direct with no GOOGLE_API_KEY, malformed combos). Note: an inference-
    gateway id that is syntactically fine but rejected by the gateway fails at the
    runtime handshake, not at build — the network-gated CI probe (task 7.3) is the
    backstop for that. Returns (component, specs_used) so model_names reflects
    whatever actually built.
    """
    defaults = normalize_specs(kind, default_specs)
    try:
        specs = normalize_specs(kind, raw_specs) or defaults
    except SpecError as e:
        # Malformed pinned spec — degrade, never crash start (no SIP fallback net).
        logger.error(
            "Pipeline %s spec is invalid (%s); falling back to the built-in default "
            "chain.", kind, e,
        )
        return builder(defaults), defaults
    try:
        return builder(specs), specs
    except Exception as e:  # noqa: BLE001 — degrade on any build failure, never crash start
        ids = [f"{s.get('provider','?')}/{s.get('model','?')}" for s in specs]
        if specs == defaults:
            # The specs that failed ARE the defaults (no real pin to degrade to).
            # This is a platform-level failure (e.g. missing LIVEKIT_API_KEY breaks
            # every gateway build), not a bad pinned id — fail loud, don't mask.
            logger.critical("Pipeline %s default chain failed to build (%s) — "
                            "platform misconfigured; cannot start.", kind, e)
            raise
        logger.error(
            "Pipeline %s build failed for %s (%s); falling back to the built-in "
            "default chain. A pinned model id may be stale or unrunnable.",
            kind, ids, e,
        )
        try:
            return builder(defaults), defaults
        except Exception as e2:  # noqa: BLE001
            # Pinned spec failed AND the default chain also fails to build — this
            # is platform-level (creds/deps), not a per-profile issue. Fail loud
            # with both causes rather than returning a None component that would
            # crash agent.py more confusingly downstream.
            logger.critical("Pipeline %s fallback default chain also failed to "
                            "build (%s) after pinned build failed (%s) — platform "
                            "misconfigured.", kind, e2, e)
            raise


# ── Resolver ───────────────────────────────────────────────
@dataclass
class ResolvedComponents:
    """Built session components + the resolved primary model names for cost.

    agent.py assembles the AgentSession (mode-specific turn handling / VAD live
    there); the resolver only builds the swappable components and reports which
    models it picked, so cost can price by the actual selection instead of the
    metrics-reported name (which is "FallbackAdapter" for any chain — see D5).

    `model_names` shape (task 2.5a — extensible for graph per-node models):
    {"schema": 1, "<kind>": [{"model": "<name>"}, ...]} where kind is
    llm/stt/tts (pipeline) or realtime/stt (realtime). Each kind holds a LIST of
    segments so a future graph session can record several models per kind (one
    per node); today the resolver records exactly one — the primary. Cost prices
    by segment [0]; per-segment attribution is graph-runtime-executor's to define.
    """

    mode: str
    llm: Any
    stt: Any
    tts: Any | None = None
    realtime_voice: str | None = None
    model_names: dict[str, Any] = field(default_factory=dict)


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

        # Route realtime STT through preflight too (review #3): realtime has no
        # FallbackAdapter net, so a malformed/unbuildable pinned STT (e.g. via:direct
        # deepgram with no DEEPGRAM_API_KEY) must degrade to the default rather than
        # crash session start on a live call.
        realtime_stt, rt_stt_used = _build_with_preflight(
            "stt", realtime_block.get("stt"), _DEFAULT_REALTIME_STT, build_stt
        )
        stt_built = _apply_stt_override(rt_stt_used[0])

        return ResolvedComponents(
            mode="realtime",
            llm=realtime_llm,
            stt=realtime_stt,
            tts=None,
            realtime_voice=rt_voice,
            model_names={
                "schema": 1,
                "realtime": _segments(rt_model),
                "stt": _segments(_model_id(stt_built)),
            },
        )

    # ── pipeline ──
    # Pass RAW specs — _build_with_preflight normalizes inside so a malformed pin
    # degrades to defaults instead of crashing session start (review #1).
    llm, llm_used = _build_with_preflight("llm", models.get("llm"), _DEFAULT_PIPELINE_LLM, build_llm)
    stt, stt_used = _build_with_preflight("stt", models.get("stt"), _DEFAULT_PIPELINE_STT, build_stt)
    tts, tts_used = _build_with_preflight("tts", models.get("tts"), _DEFAULT_PIPELINE_TTS, build_tts)

    return ResolvedComponents(
        mode="pipeline",
        llm=llm,
        stt=stt,
        tts=tts,
        model_names={
            "schema": 1,
            "llm": _segments(_model_id(llm_used[0]) if llm_used else None),
            "stt": _segments(_model_id(stt_used[0]) if stt_used else None),
            "tts": _segments(_model_id(tts_used[0]) if tts_used else None),
        },
    )
