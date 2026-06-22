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
    KNOWN_DIRECT_PROVIDERS,
    REALTIME_LLM_PROVIDERS,
    REALTIME_MODEL_ALLOWLIST,
)

logger = logging.getLogger("api.model_defaults")

router = APIRouter(prefix="/api/model-defaults", tags=["model-defaults"])


def _primary(specs) -> dict:
    """The primary (segment[0]) spec the UI shows as the inherited value."""
    if isinstance(specs, list):
        return dict(specs[0]) if specs else {}
    return dict(specs or {})


def _llm_options() -> list[dict]:
    """Priced LLM choices, derived from the cost table keys (`provider/model`)."""
    out: list[dict] = []
    for key in sorted(LLM_RATES):
        provider, _, model = key.partition("/")
        if provider and model:
            out.append({"provider": provider, "model": model})
    return out


def build_model_catalog() -> dict:
    """Assemble the model catalog from the authoritative backend constants.

    Pure reflection of existing constants + cost tables; importing this never
    instantiates a component or requires a provider key (import-light).
    """
    return {
        "schema": 1,
        "direct_providers": sorted(KNOWN_DIRECT_PROVIDERS),
        "pipeline": {
            "defaults": {
                "llm": _primary(DEFAULT_PIPELINE_LLM),
                "stt": _primary(DEFAULT_PIPELINE_STT),
                "tts": _primary(DEFAULT_PIPELINE_TTS),
            },
            "llm_options": _llm_options(),
            "stt_providers": sorted(STT_RATES),
            "tts_providers": sorted(TTS_RATES),
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
