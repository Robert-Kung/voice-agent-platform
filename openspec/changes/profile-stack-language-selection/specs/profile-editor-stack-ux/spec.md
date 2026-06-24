## ADDED Requirements

### Requirement: STT and TTS language controls

The model-stack editor SHALL provide a language control for STT (bound to `models.stt[].language`, the primary spec, consistent with how the model/voice/via controls edit `specs[0]` — fallback-chain entries keep their own language) and for pipeline TTS (bound to `models.tts.language`). The same STT control SHALL also apply to realtime STT (`models.realtime.stt.language`), since the realtime and pipeline STT fields share the editor's catalog spec control. Each control SHALL be a dropdown sourced from the per-model language capability matrix for the currently selected provider/model, plus a free-text escape hatch for codes not in the matrix. Each control's default SHALL be the selected model's first matrix entry (`zh-TW` for Deepgram general models, `zh` for `cartesia/ink-whisper`, `en` for the English-only models; TTS defaults to `zh`), matching the compiled runtime defaults; the inherited-vs-pinned distinction SHALL be shown the same way as the other stack fields. Both values SHALL round-trip through save/load, participate in the editor's `isDirty` state, and survive prune. When the provider/model is changed, the language SHALL reset to the new model's default (its first matrix entry) rather than carrying the previous language onto a model that may not support it.

#### Scenario: Pick an STT language from the matrix

- **WHEN** the user selects a language for an STT model that supports it
- **THEN** the value is written to `models.stt[].language` (primary spec) and round-trips through save/load

#### Scenario: Pick a TTS language from the matrix

- **WHEN** the user selects a language for a pipeline TTS model
- **THEN** the value is written to `models.tts.language` and round-trips through save/load

#### Scenario: Free-text language code outside the matrix

- **WHEN** the user enters a language code not present in the matrix for the selected model
- **THEN** the value is still written and round-trips, without being blocked

#### Scenario: Provider/model change resets the language to the new model's default

- **WHEN** the user changes the STT or TTS provider/model
- **THEN** the language resets to the new model's default (its first matrix entry) — e.g. switching to an English-only STT model resets the language to `en` — rather than carrying the previous value onto a model that may not support it

#### Scenario: Language edit reflects in dirty state

- **WHEN** the user changes an STT or TTS language field
- **THEN** the editor's unsaved/dirty indicator reflects the change via the existing `isDirty` mechanism

### Requirement: Unsupported language combination warning

When a profile's persisted language is not in the selected model's matrix entry — a state reachable by loading an existing profile whose model/language predate the matrix, or by the user free-texting a code the model does not support (a fresh provider/model change resets to a supported default, so it does not trigger this) — the editor SHALL surface an inline advisory warning at the control. The warning SHALL NOT disable save and SHALL NOT auto-rewrite the user's value.

#### Scenario: Loaded profile with an unsupported language warns

- **WHEN** a profile loads with an STT model and a `language` the model's matrix entry does not include (e.g. an English-only model carrying a Chinese code from an older config)
- **THEN** an inline warning indicates the model does not support that language
- **AND** the save action is not disabled and the value is not auto-changed

#### Scenario: Free-text unsupported code warns but is kept

- **WHEN** the user free-texts a language code not in the selected model's matrix entry
- **THEN** an inline warning is shown, the value is still written, and save is not blocked

## MODIFIED Requirements

### Requirement: Voice settings panel

The editor SHALL provide voice settings bound to the correct `models` field per engine mode: in Realtime mode the voice is the `models.realtime.voice` field, and in Pipeline mode the voice is a **separate `models.tts.voice` field**, distinct from the TTS model id, consistent with the LiveKit Inference TTS contract (`model` + separate `voice`). The spec SHALL map each voice control to its exact `models.*` path per mode. For pipeline TTS the editor SHALL present a per-provider suggested-voice selection (from the catalog's suggested-voice list) plus a free-form entry for custom or cloned voice ids. For realtime the voice remains a free-form input (optionally with suggestions). STT and TTS **language controls are now in scope** and specified separately (see "STT and TTS language controls"), driven by the language capability matrix; a **speed** control remains out of scope (no per-provider speed capability data exists), and when added in a follow-up SHALL be shown only for providers/modes that support it (hidden or disabled otherwise) — until then no ignored speed value is written. A profile that previously encoded a voice inside the pipeline TTS model id SHALL keep working (the id stays a valid model string) and the editor SHALL surface it without destructively rewriting it, letting the user re-pick into `models.tts.voice`.

#### Scenario: Select a realtime voice

- **WHEN** the user sets the voice in Realtime mode
- **THEN** the value is written to `models.realtime.voice` and round-trips through save/load

#### Scenario: Pipeline voice is a separate field

- **WHEN** the user picks a pipeline TTS voice from the suggested list (or enters a custom id)
- **THEN** the value is written to `models.tts.voice` (separate from `models.tts.model`) and round-trips through save/load, and the runtime applies it as the TTS voice parameter

#### Scenario: Legacy model-id-encoded voice still works

- **WHEN** a profile has a pipeline TTS voice encoded in the model id (the v1 stopgap shape)
- **THEN** the editor displays it without rewriting it, the session still runs, and the user MAY re-pick into the `models.tts.voice` field

#### Scenario: Unsupported speed control is hidden or disabled

- **WHEN** the active provider/mode does not support a speed control
- **THEN** that control is hidden or disabled rather than writing an ignored value
