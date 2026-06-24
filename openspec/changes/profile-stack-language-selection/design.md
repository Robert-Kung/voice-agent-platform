## Context

The pipeline runtime already passes `language` to the LiveKit Inference gateway: `_build_one_stt` calls `inference.STT(language=…)` and `_build_one_tts` calls `inference.TTS(language=…, …)` (defaulting to `"zh"`). The per-spec `language` field is a known key in `use-profile-form` and round-trips through save/load. What is missing is purely the editor surface: `StackSettings` renders provider/model/voice/via controls but no language control, so the value is only settable by hand-editing the profile.

The prior change (`profile-model-catalog-runtime`) left an orphan clause in the `profile-editor-stack-ux` "Voice settings panel" requirement — *"Speed/language controls SHALL be shown only for providers/modes that support them"* — and its task 7.13 explicitly deferred building the control because there was no per-model capability data. That data has now been gathered from live LiveKit + provider documentation (see Decisions), so the control can be built without guessing.

Primary use case: Traditional Chinese (`zh-TW`) Taiwan phone agents. The sharpest motivating bug: `deepgram/nova-2-phonecall` sounds ideal for a phone agent but is **English-only**, and today nothing stops a zh-TW deployment from selecting it and silently transcribing in the wrong language.

## Goals / Non-Goals

**Goals:**
- A per-model language **capability matrix** in the authoritative catalog (backend source of truth + frontend mirror + shared fixture, contract-tested both sides).
- An STT language picker and a TTS language picker in `StackSettings`, driven by the matrix, defaulting sensibly for zh-TW, with a free-text escape hatch.
- A visible warning when a selected language is not in the chosen model's supported set (e.g. an English-only STT model under a zh-TW agent) — advisory, never a hard block.
- Clean round-trip + provider-change reset for `models.stt[].language` and `models.tts.language`, consistent with the existing voice/via fields.

**Non-Goals:**
- Changing any runtime build path (language passthrough already works).
- A live language-probe test (unlike model ids, the gateway has no cheap per-language acceptance check; the matrix is advisory + escape-hatch backed).
- TTS voice picker (already shipped), speed controls, hiding non-Chinese TTS providers from voice suggestions (deferred follow-up), and 3.1-flash-live-preview realtime (upstream/Google-blocked, livekit/agents#5260).

## Decisions

### D1: Matrix is per-`provider/model`, not per-provider
STT capability is **not** uniform within a provider: `deepgram/nova-3` and `deepgram/nova-2` support `zh-TW`/`zh-Hant`/`zh-CN`/`zh-HK`, but `deepgram/nova-2-phonecall`, `nova-2-medical`, `nova-2-conversationalai`, and `nova-3-medical` are English-only. TTS Chinese support also varies within a provider (`elevenlabs/eleven_flash_v2_5` supports `zh`, `eleven_flash_v2` does not). So the matrix is keyed per `provider/model`. To avoid repetition, shared language lists are defined once and referenced (a small set of named lists: e.g. `DEEPGRAM_GENERAL_LANGS`, `EN_ONLY`, `CARTESIA_LANGS`).
- *Alternative considered*: per-provider matrix — rejected, it cannot express the English-only specialty Deepgram models, which is the core trap this change fixes.

### D2: Language codes are BCP-47, advisory not enforced
LiveKit normalizes any of ISO 639-1 / BCP-47 / language names to BCP-47 before sending to the provider, so the matrix stores BCP-47 codes (`zh-TW`, `zh-Hant`, `en-US`, …). The picker offers the matrix list but keeps a **free-text escape hatch**: the matrix is a curated convenience + warning source, not a validator. The save-time validator continues to guarantee shape only (consistent with `profile-model-config`), not language runnability.
- *Alternative considered*: hard-reject unsupported languages at save — rejected, it breaks the escape hatch and would block legitimately-newer codes the matrix hasn't caught up to.

### D3: Per-model default = the matrix list's first entry; provider change resets to it
Each model's matrix language list is ORDERED so `supportedLanguages[0]` is its sensible default (`zh-TW` for Deepgram general, `zh` for cartesia ink-whisper, `en` for the English-only specialty models; TTS `zh`). The picker derives the default from the matrix — no separate default field. On a provider/model change the language **resets to the new model's default** rather than carrying the prior value onto a model that may not support it (decision: reset over keep-and-warn — keeping an unsupported value on a fresh selection is the surprising state; a model that genuinely can't do the target language, e.g. nova-2-phonecall for Chinese, is the user's model choice to correct).
- *Alternative considered*: keep the prior language and warn on provider change — rejected for the fresh-selection case (silently invalid combo); the warning is retained for the states reset cannot reach (D4).

### D4: Warning covers only the states a reset cannot reach
Because a provider/model change resets to a supported default (D3), an unsupported combination only persists when (a) an existing profile loads with a model/language pair from before the matrix, or (b) the user free-texts a code the model does not support. In those cases the control shows an inline advisory warning ("此模型不支援此語言" / "language not supported by this model"); it does not disable save and does not auto-rewrite the value — consistent with D2's advisory stance and the non-destructive legacy-voice handling.

### D5b: Realtime STT shares the control
The realtime and pipeline STT fields render through the same catalog spec control, so the STT language control also applies to `models.realtime.stt.language` (realtime STT is Deepgram, default `zh-TW`). This is in scope because it is near-free given the shared control, and realtime STT had the same missing-control gap. The realtime LLM/voice path is unaffected (no STT language change there).

### D5: Matrix served + mirrored exactly like the model catalog
The matrix is added next to `MODEL_CATALOG` in `runtime/constants.py`, served by `routes_model_defaults.build_model_catalog()`, mirrored in `frontend/lib/__fixtures__/backend-model-constants.json` and `frontend/lib/model-catalog.ts` `FALLBACK_MODEL_CATALOG`. The existing pytest (backend matches fixture) and vitest (fallback matches fixture) contract tests are extended to cover the matrix, so drift in either direction fails a test.

### D6: Round-trip reuses the existing `language` plumbing
`language` is already a known per-spec key in `use-profile-form`; the work is wiring the two UI controls to `updateModelSpec('stt'|'tts', { language })`, ensuring `isDirty`/`pruneModels` treat it as meaningful, and that a provider change resets a now-invalid language to the new model's default (same reset path that already clears stale voice/model on provider switch).

## Risks / Trade-offs

- **Matrix drift from provider reality** (a provider adds/drops a language) → Mitigation: matrix is advisory (warn, not block) + free-text escape hatch; record the source + collection date in a comment, same convention as the model-id catalog.
- **No live verification for languages** (unlike the model-id gateway probe) → Mitigation: accept advisory status explicitly; the runtime already passes whatever code is set, and LiveKit normalizes it. A wrong language degrades transcription quality, it does not drop the call.
- **Per-model granularity bloats the catalog payload** → Mitigation: shared named lists referenced by multiple models keep the data compact; the endpoint emits the resolved per-model lists.
- **Two sources for "supported languages" (matrix vs provider truth)** could imply false completeness → Mitigation: the picker copy frames the list as "suggested/known" with free-text always available, never "the only valid values."
