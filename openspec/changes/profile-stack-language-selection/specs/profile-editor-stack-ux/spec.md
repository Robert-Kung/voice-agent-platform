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

The editor SHALL provide voice settings bound to the correct `models` field per engine mode: in Realtime mode the voice is the `models.realtime.voice` field, and in Pipeline mode the voice is carried by the TTS selection (`models.tts`, where many providers encode the voice in the `model` field). The spec SHALL map each voice control to its exact `models.*` path per mode rather than leaving it generic. Because no curated voice catalog exists in the codebase today (realtime voice is a free-form string, pipeline TTS voices are encoded in the model id), v1 SHALL provide a free-form voice input (optionally with suggestions) for realtime and the provider/model selector for pipeline TTS. A metadata-rich searchable catalog (language/gender/accent badges) and sample playback are deferred extensions, NOT v1 requirements, and the spec SHALL NOT imply metadata is shown when no catalog source exists. Language controls for STT and TTS are specified separately (see "STT and TTS language controls") and are driven by the language capability matrix; a speed control SHALL be shown only for providers/modes that support it (hidden or disabled otherwise).

#### Scenario: Select a realtime voice

- **WHEN** the user sets the voice in Realtime mode
- **THEN** the value is written to `models.realtime.voice` and round-trips through save/load

#### Scenario: Pipeline voice via TTS selection

- **WHEN** the user picks a pipeline TTS provider/model that encodes a voice
- **THEN** the voice is carried by `models.tts` and round-trips through save/load, without a separate conflicting voice field

#### Scenario: Unsupported control is hidden or disabled

- **WHEN** the active provider/mode does not support a speed control
- **THEN** that control is hidden or disabled rather than writing an ignored value
