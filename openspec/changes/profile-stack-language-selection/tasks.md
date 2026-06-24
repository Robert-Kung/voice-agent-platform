> Builds on `profile-model-catalog-runtime`. Runtime already passes `language` to the gateway (providers.py `_build_one_stt`/`_build_one_tts`); this change is the capability matrix + editor UI only. No build-path change.

## 1. Backend capability matrix (source of truth)

- [ ] 1.1 Add a per-`provider/model` language matrix to `runtime/constants.py` beside `MODEL_CATALOG`: STT models → BCP-47 code lists (deepgram nova-3/nova-2 → zh-TW/zh-Hant/zh-CN/zh-HK + en; nova-2-phonecall/-medical/-conversationalai/nova-3-medical → en-only; cartesia/ink-whisper → zh + others), TTS models → code lists with Chinese where supported (cartesia sonic*, elevenlabs *_v2_5/multilingual_v2, inworld 1.5* include zh; aura-2, rime*, elevenlabs non-v2_5 exclude zh). Use shared named lists to keep it compact. Comment the source + collection date.
- [ ] 1.2 Extend `api/routes_model_defaults.build_model_catalog()` to serve the matrix (per-model supported-language lists) under the pipeline catalog, derived from the constants (no second hardcoded copy).
- [ ] 1.3 Mirror the matrix in `frontend/lib/__fixtures__/backend-model-constants.json`.

## 2. Frontend catalog + types

- [ ] 2.1 Expand `frontend/lib/model-catalog.ts` types + `FALLBACK_MODEL_CATALOG` with the matrix; keep it matching the shared fixture (vitest contract).
- [ ] 2.2 Add a catalog helper to resolve "supported languages for provider/model" + "is `language` supported by provider/model" for the UI to consume.

## 3. Frontend form round-trip

- [ ] 3.1 `frontend/hooks/use-profile-form.ts`: ensure `models.stt[].language` and `models.tts.language` round-trip, are covered by `isDirty`, survive `pruneModels`, and that a provider/model change resets a now-unsupported language to the new model's default (reuse the existing voice/model reset path).

## 4. Frontend UI (StackSettings)

- [ ] 4.1 STT language control: matrix-driven dropdown + free-text escape hatch, bound to `models.stt[].language`, default `zh-TW` on Deepgram general models, inherited/pinned shown like other fields.
- [ ] 4.2 TTS language control: matrix-driven dropdown + free-text escape hatch, bound to `models.tts.language`, default `zh`.
- [ ] 4.3 Unsupported-combination warning: inline advisory at the control when the selected language is not in the model's matrix entry (e.g. a zh code on `deepgram/nova-2-phonecall`); never disables save, never auto-rewrites.

## 5. Tests & verification

- [ ] 5.1 pytest: catalog/matrix parity vs fixture; matrix shape assertions (deepgram general include zh-TW; specialty deepgram en-only; TTS Chinese-capable vs not); validator still does NOT reject an unenumerated language code.
- [ ] 5.2 vitest: catalog round-trip incl. stt/tts `language`; matrix contract vs shared fixture; provider-change reset of unsupported language; warning logic (zh on en-only STT) ; free-text passthrough.
- [ ] 5.3 frontend build passes.
- [ ] 5.4 Browser QA: STT + TTS language dropdowns sourced from matrix, default zh-TW/zh; round-trip to `models.stt[].language` / `models.tts.language`; English-only STT model (nova-2-phonecall) shows the warning under a zh language; free-text code accepted; values applied in a Try ▶ session.
- [ ] 5.5 `openspec validate profile-stack-language-selection --strict` passes.
