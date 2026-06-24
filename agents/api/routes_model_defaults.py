"""Read-only model-defaults endpoint (profile-editor-stack-ux, D-T1).

Single source of truth for the profile editor's model/voice UI: the compiled
built-in defaults plus the legal provider / model / realtime-variant lists. This
endpoint adds NO runtime behavior — it only reflects the existing import-light
constants (`runtime.constants`) and the cost rate tables (`db.cost`) so the
frontend never hardcodes a second copy that can silently drift (the same parity
discipline this change applies to the graph validator).

The exposed defaults are the *compiled* defaults; a deployment-layer env override
(GOOGLE_REALTIME_MODEL / GOOGLE_REALTIME_VOICE) can shadow them at runtime, so the
UI must present them as inherited-not-guaranteed, not runtime-effective.
"""

import logging

from fastapi import APIRouter

from db.cost import LLM_RATES, STT_RATES, TTS_RATES
from runtime.constants import (
    DEFAULT_PIPELINE_LLM,
    DEFAULT_PIPELINE_STT,
    DEFAULT_PIPELINE_TTS,
    DEFAULT_REALTIME_MODEL,
    DEFAULT_REALTIME_STT,
    DEFAULT_REALTIME_VOICE,
    DIRECT_BUILDABLE,
    KNOWN_DIRECT_PROVIDERS,
    MODEL_CATALOG,
    MODEL_LANGUAGES,
    REALTIME_LLM_PROVIDERS,
    REALTIME_MODEL_ALLOWLIST,
    SUGGESTED_VOICES,
)

logger = logging.getLogger("api.model_defaults")

router = APIRouter(prefix="/api/model-defaults", tags=["model-defaults"])


def _primary(specs) -> dict:
    """The primary (segment[0]) spec the UI shows as the inherited value."""
    if isinstance(specs, list):
        return dict(specs[0]) if specs else {}
    return dict(specs or {})


def _priced(kind: str, provider: str, model: str) -> bool:
    """Whether a cost rate exists for a catalog model. LLM is model-granular
    (`provider/model` rate keys); STT/TTS are provider-granular (rate tables keyed
    by provider only — a documented approximation, design D7). A green flag on an
    STT/TTS model means "this provider is priced", not "this exact model's rate"."""
    if kind == "llm":
        # EXACT membership, not the fuzzy cost matcher: a model is "priced" only
        # if it has its OWN rate key. Using _match_llm_rate here would let a
        # shorter key (gpt-4.1) substring-match a distinct model (gpt-4.1-nano)
        # and falsely flag it priced (review F-nano).
        return f"{provider}/{model}" in LLM_RATES
    if kind == "stt":
        return provider in STT_RATES
    if kind == "tts":
        return provider in TTS_RATES
    return False


def _catalog_kind(kind: str) -> dict[str, list[dict]]:
    """MODEL_CATALOG[kind] as a provider-keyed map of priced-annotated models —
    the shape the cascade UI consumes (pick provider → its models).

    The catalog (runtime.constants.MODEL_CATALOG) is the authoritative runnable
    set; cost only ANNOTATES it. We do NOT derive the list from cost keys — that
    cannot express an unpriced-but-runnable model (design D7 / review H1)."""
    return {
        provider: [
            {"model": model, "priced": _priced(kind, provider, model)}
            for model in MODEL_CATALOG[kind][provider]
        ]
        for provider in sorted(MODEL_CATALOG.get(kind, {}))
    }


def _flat_llm_options() -> list[dict]:
    """Legacy compat: flat provider/model list for the v1 llm_options field."""
    return [
        {"provider": p, "model": m}
        for p in sorted(MODEL_CATALOG["llm"])
        for m in MODEL_CATALOG["llm"][p]
    ]


def build_model_catalog() -> dict:
    """Assemble the model catalog from the authoritative backend constants.

    Pure reflection of existing constants + cost tables; importing this never
    instantiates a component or requires a provider key (import-light). schema 2
    adds the full `pipeline.catalog` (priced-annotated) + per-provider `voices`;
    the legacy `llm_options`/`stt_providers`/`tts_providers` remain for compat but
    are now sourced from MODEL_CATALOG, not cost keys.
    """
    catalog = {kind: _catalog_kind(kind) for kind in ("llm", "stt", "tts")}
    return {
        "schema": 2,
        "direct_providers": sorted(KNOWN_DIRECT_PROVIDERS),
        # (kind, provider) pairs with a wired direct build path; the UI shows the
        # via:direct toggle only for these (e.g. "llm:google").
        "direct_buildable": sorted(f"{k}:{p}" for k, p in DIRECT_BUILDABLE),
        "pipeline": {
            "defaults": {
                "llm": _primary(DEFAULT_PIPELINE_LLM),
                "stt": _primary(DEFAULT_PIPELINE_STT),
                "tts": _primary(DEFAULT_PIPELINE_TTS),
            },
            "catalog": catalog,
            "voices": {p: list(vs) for p, vs in SUGGESTED_VOICES.items()},
            # Per-model language capability matrix (advisory), kind→provider→model→
            # ordered BCP-47 list ([0] = default). Drives the editor language pickers.
            "languages": {
                kind: {
                    provider: {model: list(langs) for model, langs in models.items()}
                    for provider, models in MODEL_LANGUAGES[kind].items()
                }
                for kind in ("stt", "tts")
            },
            # Legacy (compat): provider lists + flat llm list, now from catalog.
            "llm_options": _flat_llm_options(),
            "stt_providers": sorted(MODEL_CATALOG["stt"]),
            "tts_providers": sorted(MODEL_CATALOG["tts"]),
        },
        "realtime": {
            "defaults": {
                "model": DEFAULT_REALTIME_MODEL,
                "voice": DEFAULT_REALTIME_VOICE,
                "stt": dict(DEFAULT_REALTIME_STT),
            },
            "llm_providers": sorted(REALTIME_LLM_PROVIDERS),
            # Only variants that are BOTH allowlisted (runtime accepts) AND priced
            # (cost won't silently fall to the default rate). Surfacing an
            # un-priced allowlisted variant would let the UI offer a mispriced
            # option — the realtime variant ↔ cost-rate sync this guards.
            "model_allowlist": sorted(REALTIME_MODEL_ALLOWLIST),
            "voice_suggestions": ["Kore", "Puck", "Charon", "Aoede", "Fenrir"],
        },
    }


@router.get("")
def get_model_defaults():
    catalog = build_model_catalog()
    logger.info(
        "model-defaults: %d llm options, %d realtime variants",
        len(catalog["pipeline"]["llm_options"]),
        len(catalog["realtime"]["model_allowlist"]),
    )
    return catalog
