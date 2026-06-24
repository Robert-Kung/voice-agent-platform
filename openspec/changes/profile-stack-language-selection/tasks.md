> Builds on `profile-model-catalog-runtime`. Runtime already passes `language` to the gateway (providers.py `_build_one_stt`/`_build_one_tts`); this change is the capability matrix + editor UI only. No build-path change.

## 1. Backend capability matrix (source of truth)

- [x] 1.1 Add a per-`provider/model` language matrix to `runtime/constants.py` beside `MODEL_CATALOG`, each list ORDERED so `[0]` is the model's default: STT models → BCP-47 lists (deepgram nova-3/nova-2 → [zh-TW, zh-Hant, zh-CN, zh-HK, en, …]; nova-2-phonecall/-medical/-conversationalai/nova-3-medical → [en, en-US] only; cartesia/ink-whisper → [zh, …]), TTS models → lists with Chinese where supported, default first (cartesia sonic*, elevenlabs *_v2_5/multilingual_v2, inworld 1.5* → [zh, …]; aura-2, rime*, elevenlabs non-v2_5 → no zh). Use shared named lists to keep it compact. Comment the source + collection date.
- [x] 1.2 Extend `api/routes_model_defaults.build_model_catalog()` to serve the matrix (per-model supported-language lists) under the pipeline catalog, derived from the constants (no second hardcoded copy).
- [x] 1.3 Mirror the matrix in `frontend/lib/__fixtures__/backend-model-constants.json`.

## 2. Frontend catalog + types

- [x] 2.1 Expand `frontend/lib/model-catalog.ts` types + `FALLBACK_MODEL_CATALOG` with the matrix; keep it matching the shared fixture (vitest contract).
- [x] 2.2 Add a catalog helper to resolve "supported languages for provider/model" + "is `language` supported by provider/model" for the UI to consume.

## 3. Frontend form round-trip

- [x] 3.1 `frontend/hooks/use-profile-form.ts`: ensure `models.stt[].language` (primary spec) and `models.tts.language` round-trip, are covered by `isDirty`, survive `pruneModels`, and that a provider/model change resets the language to the new model's default (matrix `[0]`), reusing the existing voice/model reset path (`onProviderChange` already resets model+voice — add language).

## 4. Frontend UI (StackSettings)

- [x] 4.1 STT language control in the shared catalog spec field (so it covers BOTH pipeline `models.stt[].language` AND realtime `models.realtime.stt.language`): matrix-driven dropdown + free-text escape hatch, default = model's matrix `[0]` (zh-TW for Deepgram general, en for en-only, zh for cartesia), inherited/pinned shown like other fields.
- [x] 4.2 TTS language control: matrix-driven dropdown + free-text escape hatch, bound to `models.tts.language`, default `zh` (matrix `[0]`).
- [x] 4.3 Unsupported-combination warning: inline advisory only for states a reset can't reach — a LOADED profile whose persisted language is outside the model's matrix entry, or a free-texted unsupported code (e.g. a zh code on `deepgram/nova-2-phonecall`); never disables save, never auto-rewrites. (A fresh provider/model change resets to a supported default, so it never warns.)

## 5. Tests & verification

- [x] 5.1 pytest: catalog/matrix parity vs fixture; matrix shape assertions (deepgram general include zh-TW; specialty deepgram en-only; TTS Chinese-capable vs not); validator still does NOT reject an unenumerated language code.
- [x] 5.2 vitest: catalog round-trip incl. stt/tts `language`; matrix contract vs shared fixture; provider-change resets language to new model's `[0]`; warning logic for a LOADED unsupported pair + free-text unsupported code; free-text passthrough; per-model default derivation (`[0]`).
- [x] 5.3 frontend build passes.
- [ ] 5.4 Browser QA: STT + TTS language dropdowns sourced from matrix, default = model's first entry (zh-TW deepgram / zh cartesia&tts); realtime STT language control present too; round-trip to `models.stt[].language` / `models.tts.language` / `models.realtime.stt.language`; switching to nova-2-phonecall resets language to en; a profile loaded with zh on an en-only model shows the warning; free-text code accepted; values applied in a Try ▶ session.
- [x] 5.5 `openspec validate profile-stack-language-selection --strict` passes.
