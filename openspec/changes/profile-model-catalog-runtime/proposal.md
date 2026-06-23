## Why

`profile-editor-model-voice-ux` (archived 2026-06-18) shipped the model/voice stack UI under a hard "zero backend runtime change" constraint, so it had to use stopgaps: pipeline provider/model are typed against a tiny hardcoded list, the pipeline voice is assumed to be *encoded in the TTS model id*, and there is no way to use Google's direct API key from the editor. We run on **LiveKit Cloud**, where the LiveKit Inference gateway is the authoritative set of runnable models — so "what you can pick" should equal "what actually runs". Research of the LiveKit Inference docs surfaced two facts that break the v1 stopgaps and require backend work to fix properly: TTS **voice is a separate parameter** (not part of the model id, with a curated suggested-voices table), and the gateway exposes a large, enumerable provider/model catalog. This change makes the picker real and guaranteed-runnable.

## What Changes

- **Enumerable provider + model dropdowns** (not hand-typed) for pipeline LLM/STT/TTS, sourced from a curated backend catalog of the LiveKit Inference models, served by **extending the existing read-only `GET /api/model-defaults`** endpoint. Drift is guarded by the same shared-fixture contract test (pytest + vitest) the prior change established.
- **All LiveKit models are selectable**, including ones with no cost rate in `db/cost.py`; those are **flagged "cost estimate unavailable"** in the UI rather than hidden, and never blocked from selection (the existing `multi-model-cost` "unknown model marked incomplete" behavior already handles the runtime side). The `priced` flag is **model-granular for LLM** (rates keyed `provider/model`) and **provider-granular for STT/TTS** (rates keyed by provider only — documented approximation, see design D7); the catalog is the authoritative runnable set and cost *annotates* it (the endpoint stops deriving the LLM list from cost keys).
- **First-class voice picker.** **BREAKING (v1 stopgap):** the pipeline TTS voice moves out of the model id into a separate `models.tts.voice` field, surfaced from the per-provider suggested-voices list plus a free-form entry for custom/cloned voices. Realtime voice stays `models.realtime.voice`. This requires a backend runtime change to pass `voice` through to `inference.TTS` in `runtime/providers.py`.
- **Google direct-API-key toggle.** A google LLM/TTS spec can switch between `via:inference` (LiveKit gateway, no key) and `via:direct` (`GOOGLE_API_KEY` from `.env`). This requires wiring the google-direct build path in `runtime/providers.py` (today `_build_one_llm` raises for any non-inference provider; google-direct is realtime-only).
- **Model-id namespace reconciliation.** The catalog's exact accepted model-id strings are verified against the live LiveKit Cloud project (LiveKit docs show `gemini/2.5-flash` / `scribe-v2-realtime`; our current defaults use `google/gemini-3.1-flash-lite` / `scribe_v2_realtime`), and cost rate keys are aligned to whatever strings the runtime actually accepts.
- Preserve everything the prior change established: graph×realtime exclusivity, inherited/pinned distinction, and deployment-env-override honesty.

## Capabilities

### New Capabilities
<!-- none — this change modifies existing capabilities -->

### Modified Capabilities
- `profile-editor-stack-ux`: the model-list source of truth expands from a tiny hardcoded set to the full curated LiveKit Inference catalog served via the endpoint; the engine-mode selection UI uses enumerable provider+model dropdowns plus a per-provider `via:inference`/`via:direct` toggle for Google; the voice settings panel binds pipeline voice to a separate `models.tts.voice` field (replacing the v1 model-id-encoded mapping) with a suggested-voices picker; interaction states add cost-estimate-unavailable flagging for unpriced models.
- `model-provider-runtime`: the Inference-gateway/direct-SDK coexistence requirement extends to a Google direct-SDK build path for pipeline LLM and TTS (not just realtime), and the TTS build passes a first-class `voice` parameter through to `inference.TTS`/the direct plugin.
- `profile-model-config`: the optional `models` block recognizes `models.tts.voice` and a per-spec `via:direct` for Google in pipeline mode, validated by the existing import-light validator (no profile that the validator accepts may crash at session start).

## Impact

- **Backend (runtime, in scope this time):** `agents/runtime/providers.py` (`_build_one_llm` google-direct path, `_build_one_tts` voice passthrough), `agents/runtime/constants.py` (catalog constants + any validation for `tts.voice`/google-direct), `agents/api/routes_model_defaults.py` (serve the full catalog + suggested voices), `agents/db/cost.py` (add rate entries for newly-offered priced models; align keys to accepted model-id strings). New/updated pytest in `agents/tests/`.
- **Frontend:** `frontend/lib/model-catalog.ts` + the shared fixture (expanded catalog, voice lists, priced-flag), `frontend/components/admin/stack-settings.tsx` (provider/model dropdowns, voice picker, direct-key toggle, unpriced flag), `frontend/hooks/use-profile-form.ts` (`models.tts.voice` read/write, `via` per-spec), vitest contract + round-trip tests.
- **Dependencies:** enabling Google `via:direct` for pipeline may require the `livekit-plugins-google` LLM/TTS surface already vendored for realtime; confirm no new image bloat. `.env` `GOOGLE_API_KEY` is already present.
- **Data model:** `models` config remains free-form; new `models.tts.voice` field and `via:direct` values need no migration (older profiles without them keep working via fallback).
- **Out of scope:** per-node (graph) per-model UI, variables/data-collection UI, sample playback/audition, non-LiveKit-Inference custom provider endpoints.
