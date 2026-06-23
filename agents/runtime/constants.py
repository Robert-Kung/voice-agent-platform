"""Import-light constants + spec-shape helpers for the model runtime.

This module MUST NOT import any livekit plugin or heavy SDK. The FastAPI process
imports it to validate profile `models` blocks on save, and that must not drag
the agent's plugin import graph into the API process or require provider API
keys / `VAD.load()` downloads (plan-eng-review P2, import-coupling).

Spec shape:

    {provider, model, via, options, language}

`via` selects the build path:
  - "inference" (default): LiveKit Inference gateway, `{provider}/{model}` string.
  - "direct": provider SDK plugin + provider API key. Deliberately restricted to
    the providers actually in use (see KNOWN_DIRECT_PROVIDERS); the full
    (kind, provider, via) registry is deferred to graph-agent-builder/OQ4.
"""

from __future__ import annotations

VIA_INFERENCE = "inference"
VIA_DIRECT = "direct"
VALID_VIA = (VIA_INFERENCE, VIA_DIRECT)
DEFAULT_VIA = VIA_INFERENCE

KINDS = ("llm", "stt", "tts")

# Providers we support over a DIRECT SDK connection. Everything else must go via
# the Inference gateway. Kept small on purpose — adding a direct provider means a
# new plugin dependency (image bloat), so we only carry the two already needed:
# deepgram (Try-button local STT) and google (realtime Gemini Live).
KNOWN_DIRECT_PROVIDERS = {"deepgram", "google"}

# Gemini Live variants known to work with the TextInputRealtimeModel text-input
# path AND priced in db/cost.py REALTIME_RATES. 3.1-live is excluded:
# generate_reply() routes through send_client_content, which 3.1 blocks → 1007
# mid-session (see agent.py notes). Realtime has NO FallbackAdapter net, so a bad
# variant kills the call — this allowlist is the gate (plan-eng-review P3).
# Only list variants we actually run AND can price; adding one means adding its
# rate to REALTIME_RATES in the same change (code-review: don't allow what we
# can't price, or cost silently falls to the default rate).
REALTIME_MODEL_ALLOWLIST = {
    "gemini-2.5-flash-native-audio-preview-12-2025",
}

# Providers accepted for the realtime LLM. Locked to Gemini by the
# TextInputRealtimeModel architecture (design D3).
REALTIME_LLM_PROVIDERS = {"google", "gemini"}

# Compiled built-in defaults (backfill). Kept here (import-light) rather than in
# providers.py so both the runtime resolver AND the read-only model-defaults
# endpoint read ONE source — a hardcoded second copy is the drift bug this
# change's source-of-truth requirement exists to prevent. These are plain dicts
# (no plugin imports); providers.py imports them and runs them through the same
# build path, so a profile WITHOUT a models block stays byte-for-byte identical
# (regression: tests/test_runtime_providers.py default-resolution asserts).
DEFAULT_PIPELINE_LLM = [
    {"provider": "google", "model": "gemini-3.1-flash-lite", "via": VIA_INFERENCE},
    {"provider": "openai", "model": "gpt-4.1-mini", "via": VIA_INFERENCE},
]
DEFAULT_PIPELINE_STT = [
    {"provider": "elevenlabs", "model": "scribe_v2_realtime", "via": VIA_INFERENCE, "language": "zh"},
    {"provider": "deepgram", "model": "nova-2", "via": VIA_INFERENCE, "language": "zh-TW"},
]
DEFAULT_PIPELINE_TTS = [
    {"provider": "cartesia", "model": "sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc", "via": VIA_INFERENCE, "language": "zh"},
    {"provider": "elevenlabs", "model": "eleven_multilingual_v2", "via": VIA_INFERENCE, "language": "zh"},
]
DEFAULT_REALTIME_STT = {"provider": "deepgram", "model": "nova-2", "via": VIA_INFERENCE, "language": "zh-TW"}

# Realtime model/voice compiled defaults. A deployment-layer env override
# (GOOGLE_REALTIME_MODEL / GOOGLE_REALTIME_VOICE) can shadow these at runtime —
# the model-defaults endpoint surfaces them as the *compiled* default, not a
# guaranteed runtime-effective value (see profile-editor-stack-ux spec D2).
DEFAULT_REALTIME_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
DEFAULT_REALTIME_VOICE = "Kore"


# ── LiveKit Inference catalog (curated, import-light) ──────
# The authoritative set of pipeline provider/models the editor offers. Verified
# against the installed livekit-agents 1.5.2 SDK accepted set (the `*Models`
# Literal types in inference/{llm,stt,tts}.py); the namespace is `provider/model`.
# This is the SOURCE OF TRUTH for the catalog — routes_model_defaults reflects it
# and cost (db/cost.py) ANNOTATES it with a priced flag (do NOT derive the catalog
# from cost keys; that can't express unpriced-but-runnable models).
# Plain dicts only — no plugin imports (the FastAPI process imports this on save).
# `google/gemini-3.1-flash-lite` is the current shipping default; kept here as a
# known-good extra though it's dropped from the SDK 1.5.2 Literal (str is accepted).
MODEL_CATALOG: dict[str, dict[str, list[str]]] = {
    "llm": {
        "openai": [
            "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
            "gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5.1", "gpt-5.1-chat-latest",
            "gpt-5.2", "gpt-5.2-chat-latest", "gpt-5.3-chat-latest", "gpt-5.4",
            "gpt-oss-120b",
        ],
        "google": [
            "gemini-3-pro", "gemini-3-flash", "gemini-2.5-pro", "gemini-2.5-flash",
            "gemini-2.5-flash-lite", "gemini-3.1-flash-lite",
        ],
        "moonshotai": ["kimi-k2-instruct"],
        "deepseek-ai": ["deepseek-v3", "deepseek-v3.2"],
    },
    "stt": {
        "deepgram": [
            "nova-3", "nova-3-medical", "nova-2", "nova-2-medical",
            "nova-2-conversationalai", "nova-2-phonecall", "flux-general",
            "flux-general-en",
        ],
        "cartesia": ["ink-whisper"],
        "assemblyai": [
            "universal-streaming", "universal-streaming-multilingual", "u3-rt-pro",
        ],
        "elevenlabs": ["scribe_v2_realtime"],
    },
    "tts": {
        "cartesia": ["sonic-3", "sonic-2", "sonic-turbo", "sonic"],
        "deepgram": ["aura", "aura-2"],
        "elevenlabs": [
            "eleven_flash_v2", "eleven_flash_v2_5", "eleven_turbo_v2",
            "eleven_turbo_v2_5", "eleven_multilingual_v2",
        ],
        "rime": ["arcana", "mistv2"],
        "inworld": [
            "inworld-tts-1.5-max", "inworld-tts-1.5-mini", "inworld-tts-1-max",
            "inworld-tts-1",
        ],
    },
}

# Per-provider suggested TTS voices (docs.livekit.io/agents/models/tts). `id` is
# the bare value for the inference.TTS `voice=` kwarg; a free-form entry in the UI
# covers custom/cloned ids. LiveKit also documents these as `provider/model:id`.
SUGGESTED_VOICES: dict[str, list[dict[str, str]]] = {
    "cartesia": [
        {"id": "a167e0f3-df7e-4d52-a9c3-f949145efdab", "label": "Blake — Energetic American adult male"},
        {"id": "5c5ad5e7-1020-476b-8b91-fdcbe9cc313c", "label": "Daniela — Calm, trusting Mexican female"},
        {"id": "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc", "label": "Jacqueline — Confident, young American female"},
        {"id": "f31cc6a7-c1e8-4764-980c-60a361443dd1", "label": "Robyn — Neutral, mature Australian female"},
    ],
    "deepgram": [
        {"id": "apollo", "label": "Apollo — Comfortable, casual male"},
        {"id": "athena", "label": "Athena — Smooth, professional female"},
        {"id": "odysseus", "label": "Odysseus — Calm, professional male"},
        {"id": "theia", "label": "Theia — Expressive, polite female"},
    ],
    "elevenlabs": [
        {"id": "Xb7hH8MSUJpSbSDYk0k2", "label": "Alice — Clear, friendly British woman"},
        {"id": "iP95p4xoKVk53GoZ742B", "label": "Chris — Natural, real American male"},
        {"id": "cjVigY5qzO86Huf0OWal", "label": "Eric — Smooth tenor Mexican male"},
        {"id": "cgSgspJ2msm6clMCkdW9", "label": "Jessica — Young, playful American female"},
    ],
    "rime": [
        {"id": "astra", "label": "Astra — Chipper, upbeat American female"},
        {"id": "celeste", "label": "Celeste — Chill Gen-Z American female"},
        {"id": "luna", "label": "Luna — Chill but excitable American female"},
        {"id": "ursa", "label": "Ursa — Young, emo American male"},
    ],
    "inworld": [
        {"id": "Ashley", "label": "Ashley — Warm, natural American female"},
        {"id": "Diego", "label": "Diego — Soothing, gentle Mexican male"},
        {"id": "Edward", "label": "Edward — Fast-talking, emphatic American male"},
        {"id": "Olivia", "label": "Olivia — Upbeat, friendly British female"},
    ],
}

# (kind, provider) pairs the runtime can build over a DIRECT SDK connection.
# Single source consumed by normalize_spec (save-time reject) AND providers.build_*
# (build-time dispatch); a test asserts the two agree. Adding a pair means wiring
# the matching branch in providers.py + carrying its plugin dependency.
DIRECT_BUILDABLE: set[tuple[str, str]] = {("stt", "deepgram"), ("llm", "google")}


class SpecError(ValueError):
    """Raised when a model spec is malformed or names an unsupported combo."""


def normalize_spec(kind: str, spec: dict) -> dict:
    """Normalize one raw model-spec dict. Pure dict work, no component build.

    Defaults `via` to "inference". Raises SpecError on malformed shape or an
    unsupported direct provider.
    """
    if kind not in KINDS:
        raise SpecError(f"unknown spec kind '{kind}', expected one of {KINDS}")
    if not isinstance(spec, dict):
        raise SpecError(f"{kind} spec must be a mapping, got {type(spec).__name__}")

    provider = spec.get("provider")
    model = spec.get("model")
    if not provider or not isinstance(provider, str):
        raise SpecError(f"{kind} spec missing a string 'provider'")
    if not model or not isinstance(model, str):
        raise SpecError(f"{kind} spec missing a string 'model'")

    via = (spec.get("via") or DEFAULT_VIA)
    if not isinstance(via, str):
        raise SpecError(f"{kind} spec 'via' must be a string")
    via = via.strip().lower()
    if via not in VALID_VIA:
        raise SpecError(f"{kind} spec has invalid via '{via}', expected one of {VALID_VIA}")
    # Kind-aware direct support — must match exactly what providers.build_* can
    # build, or a profile would pass save-time validation then crash at session
    # start (no FallbackAdapter net on a SIP call). The DIRECT_BUILDABLE matrix is
    # the single source shared with providers.py (test asserts they agree):
    # (stt, deepgram) and (llm, google). tts via:direct stays unsupported in v1.
    if via == VIA_DIRECT and (kind, provider) not in DIRECT_BUILDABLE:
        buildable = sorted(f"{k}:{p}" for k, p in DIRECT_BUILDABLE)
        raise SpecError(
            f"{kind} spec: via:direct is not supported for '{provider}' "
            f"(direct-buildable: {buildable}); use via:inference"
        )

    options = spec.get("options") or {}
    if not isinstance(options, dict):
        raise SpecError(f"{kind} spec 'options' must be a mapping")
    # Reserved keys are passed as explicit kwargs by the builders; allowing them
    # inside options would raise a duplicate-kwarg TypeError at build time (past
    # save-time validation). Reject them up front. `voice` is reserved because
    # _build_one_tts now passes models.tts.voice as an explicit kwarg.
    reserved = {"model", "provider", "via", "language", "voice"} & set(options)
    if reserved:
        raise SpecError(f"{kind} spec 'options' may not contain reserved keys {sorted(reserved)}")

    out = {
        "kind": kind,
        "provider": provider,
        "model": model,
        "via": via,
        "options": dict(options),
    }
    language = spec.get("language")
    if language:
        out["language"] = language
    # tts voice is a first-class field (separate from the model id) passed to
    # inference.TTS(voice=). Carry it through when present; absent → model-id-only.
    voice = spec.get("voice")
    if voice is not None:
        if not isinstance(voice, str):
            raise SpecError(f"{kind} spec 'voice' must be a string")
        out["voice"] = voice
    return out


def normalize_specs(kind: str, specs) -> list[dict]:
    """Accept a single spec dict or a list of them; return a list of normalized
    specs. None/empty → []."""
    if specs is None:
        return []
    if isinstance(specs, dict):
        specs = [specs]
    if not isinstance(specs, list):
        raise SpecError(f"{kind} must be a spec mapping or a list of specs")
    return [normalize_spec(kind, s) for s in specs]


def validate_realtime_block(realtime: dict) -> None:
    """Validate a `models.realtime` block's shape. Pure checks, no build.

    Enforces the Gemini-only LLM lock (D3) and the model allowlist (P3).
    """
    if not isinstance(realtime, dict):
        raise SpecError("models.realtime must be a mapping")

    provider = realtime.get("provider")
    if provider and str(provider).strip().lower() not in REALTIME_LLM_PROVIDERS:
        raise SpecError(
            f"realtime LLM provider '{provider}' not supported — realtime is "
            f"locked to Gemini Live (TextInputRealtimeModel). Remove the provider "
            f"field or set it to 'google'."
        )

    model = realtime.get("model")
    if model and model not in REALTIME_MODEL_ALLOWLIST:
        raise SpecError(
            f"realtime model '{model}' is not in the supported allowlist "
            f"{sorted(REALTIME_MODEL_ALLOWLIST)}. Realtime has no fallback chain, "
            f"so unsupported variants (e.g. 3.1-live → 1007) are rejected at save."
        )

    stt = realtime.get("stt")
    if stt is not None:
        normalize_spec("stt", stt)


def validate_models_block(models: dict) -> None:
    """Validate an entire `models` block's shape. Raises SpecError on any problem.

    Used by both the API save path (schemas.py) and the runtime resolver, so the
    notion of "a valid spec" lives in exactly one import-light place.
    """
    if not isinstance(models, dict):
        raise SpecError("models block must be a mapping")

    mode = models.get("mode")
    if mode is not None and mode not in ("pipeline", "realtime"):
        raise SpecError(f"models.mode must be 'pipeline' or 'realtime', got '{mode}'")

    for kind in KINDS:
        if kind in models and models[kind] is not None:
            normalize_specs(kind, models[kind])

    if models.get("realtime") is not None:
        validate_realtime_block(models["realtime"])
