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
    # start (no FallbackAdapter net on a SIP call). Only deepgram STT is a direct
    # pipeline component; google-direct is realtime-only (validated separately).
    if via == VIA_DIRECT:
        if kind == "stt":
            if provider != "deepgram":
                raise SpecError(
                    f"stt spec: via:direct is only supported for deepgram, not '{provider}'; use via:inference"
                )
        else:
            raise SpecError(
                f"{kind} spec: via:direct is not supported (only deepgram STT uses direct in the "
                f"pipeline; realtime google is configured under models.realtime); use via:inference"
            )

    options = spec.get("options") or {}
    if not isinstance(options, dict):
        raise SpecError(f"{kind} spec 'options' must be a mapping")
    # Reserved keys are passed as explicit kwargs by the builders; allowing them
    # inside options would raise a duplicate-kwarg TypeError at build time (past
    # save-time validation). Reject them up front.
    reserved = {"model", "provider", "via", "language"} & set(options)
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
