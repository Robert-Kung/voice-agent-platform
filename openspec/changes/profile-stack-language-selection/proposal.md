## Why

The runtime already passes `language` to the LiveKit Inference gateway for both STT and TTS, and the per-spec `language` value round-trips through the profile form — but the model-stack editor (StackSettings) has **no UI control** to set it. A zh-TW Taiwan phone agent can only get the right recognition/pronunciation language by hand-editing the profile, and worse, can silently pick an **English-only** STT model (e.g. `deepgram/nova-2-phonecall`, whose name implies it's for phone calls) with no warning. Task 7.13 of the prior change cut the language control as an "orphan requirement" precisely because there was no per-model capability data; that data has now been collected from live LiveKit + provider docs, so the control can be built correctly.

## What Changes

- Add a **per-model language capability matrix** to the authoritative catalog: an ORDERED BCP-47 language list per STT/TTS model (first entry = that model's default) including a Chinese-support signal. Served by the model-defaults endpoint and mirrored in the frontend catalog + shared fixture (contract-tested both sides).
- Add an **STT language picker** to StackSettings (shared catalog spec control, so it covers both pipeline `models.stt[].language` and realtime `models.realtime.stt.language`): matrix-driven dropdown defaulting to the selected model's first matrix entry (`zh-TW` for Deepgram general, `en` for English-only models, `zh` for cartesia), with a free-text escape hatch.
- Add a **TTS language picker** to StackSettings: matrix-driven dropdown defaulting to `zh`, with a free-text escape hatch.
- **Provider/model change resets the language** to the new model's default; a residual unsupported language (loaded profile predating the matrix, or a free-texted code) surfaces a non-blocking advisory warning — so a zh-TW phone agent can't silently ship an English-only STT.
- Round-trip `models.stt[].language` and `models.tts.language` through the profile form (dirty-tracking, prune, and provider-change reset consistent with the existing voice/via fields).

## Capabilities

### New Capabilities
- `model-language-capability`: the per-STT-model and per-TTS-provider/model supported-language matrix (BCP-47 code lists + Chinese-support signal), surfaced through the model-defaults catalog endpoint and the frontend catalog mirror, so the editor can offer valid languages and flag unsupported combinations.

### Modified Capabilities
- `profile-editor-stack-ux`: the model-stack editor gains STT and TTS language controls (matrix-driven dropdown + free-text), with default selection, unsupported-combination warning, and round-trip/reset behavior matching the existing model/voice/via fields.

## Impact

- Backend: `agents/runtime/constants.py` (matrix data alongside `MODEL_CATALOG`), `agents/api/routes_model_defaults.py` (serve the matrix). No runtime build-path change — `providers.py` already passes `language` to `inference.STT`/`inference.TTS`.
- Frontend: `frontend/lib/model-catalog.ts` (matrix types + fallback), `frontend/lib/__fixtures__/backend-model-constants.json` (mirror), `frontend/components/admin/stack-settings.tsx` (two language controls), `frontend/hooks/use-profile-form.ts` (round-trip/reset).
- Tests: pytest catalog/matrix parity vs fixture; vitest catalog round-trip, matrix contract, language-aware enable/disable; frontend build.
- Out of scope: 3.1-flash-live-preview realtime (upstream/Google-blocked, livekit/agents#5260, no ETA — realtime allowlist already excludes it); TTS voice picker (already shipped); speed controls; hiding non-Chinese TTS providers from voice suggestions (deferred follow-up, though the per-provider language data lands here).
