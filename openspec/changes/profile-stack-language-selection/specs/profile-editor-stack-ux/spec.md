## ADDED Requirements

### Requirement: STT and TTS language controls

The model-stack editor SHALL provide a language control for pipeline STT (bound to `models.stt[].language`) and a language control for pipeline TTS (bound to `models.tts.language`). Each control SHALL be a dropdown sourced from the per-model language capability matrix for the currently selected provider/model, plus a free-text escape hatch for codes not in the matrix. The STT control SHALL default to `zh-TW` for Deepgram general models and the TTS control SHALL default to `zh`, matching the compiled runtime defaults; the inherited-vs-pinned distinction SHALL be shown the same way as the other stack fields. Both values SHALL round-trip through save/load, participate in the editor's `isDirty` state, survive prune, and reset to the new model's default when the provider/model is changed to one that does not support the current language.

#### Scenario: Pick an STT language from the matrix

- **WHEN** the user selects a language for a pipeline STT model that supports it
- **THEN** the value is written to `models.stt[].language` and round-trips through save/load

#### Scenario: Pick a TTS language from the matrix

- **WHEN** the user selects a language for a pipeline TTS model
- **THEN** the value is written to `models.tts.language` and round-trips through save/load

#### Scenario: Free-text language code outside the matrix

- **WHEN** the user enters a language code not present in the matrix for the selected model
- **THEN** the value is still written and round-trips, without being blocked

#### Scenario: Provider change resets an unsupported language

- **WHEN** the user changes the STT or TTS provider/model to one whose matrix entry does not include the current language
- **THEN** the language resets to the new model's default rather than leaving an unsupported value pinned

#### Scenario: Language edit reflects in dirty state

- **WHEN** the user changes an STT or TTS language field
- **THEN** the editor's unsaved/dirty indicator reflects the change via the existing `isDirty` mechanism

### Requirement: Unsupported language combination warning

When the selected language is not in the chosen model's matrix entry — most importantly a Chinese code on an English-only STT model such as `deepgram/nova-2-phonecall` — the editor SHALL surface an inline warning at the control. The warning SHALL be advisory: it SHALL NOT disable save and SHALL NOT auto-rewrite the user's value.

#### Scenario: English-only STT model under a Chinese language warns

- **WHEN** the user selects an English-only STT model (e.g. `deepgram/nova-2-phonecall`) while the language is a Chinese code
- **THEN** an inline warning indicates the model does not support the selected language
- **AND** the save action is not disabled and the value is not auto-changed

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
