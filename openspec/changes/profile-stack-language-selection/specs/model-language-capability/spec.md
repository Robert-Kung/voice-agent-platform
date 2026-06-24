## ADDED Requirements

### Requirement: Per-model language capability matrix

The catalog SHALL expose a per-`provider/model` language capability matrix for STT and TTS, listing the BCP-47 language codes each model is known to support. The matrix SHALL be keyed at model granularity (not provider granularity) because language support varies between models of the same provider. Each model's language list SHALL be ORDERED so the first entry is that model's sensible default (`zh-TW` first for Deepgram general models, `zh` first for `cartesia/ink-whisper`, `en`/`en-US` first for the English-only specialty models), so the editor can derive a per-model default as `supportedLanguages[0]` without a separate default field. The matrix SHALL be defined in the backend source of truth (`runtime/constants.py`, alongside `MODEL_CATALOG`), served by the model-defaults catalog endpoint, and mirrored in the frontend catalog fallback and the shared fixture, with contract tests asserting the backend, the frontend fallback, and the fixture agree.

#### Scenario: STT model-level granularity distinguishes English-only specialty models

- **WHEN** the matrix is read for Deepgram STT models
- **THEN** `deepgram/nova-3` and `deepgram/nova-2` list the Chinese codes with `zh-TW` first (the default), including `zh-Hant`
- **AND** `deepgram/nova-2-phonecall`, `deepgram/nova-2-medical`, `deepgram/nova-2-conversationalai`, and `deepgram/nova-3-medical` list only English codes
- **AND** `cartesia/ink-whisper` lists `zh` (its default) without a region subtag

#### Scenario: TTS model-level granularity distinguishes Chinese-capable models

- **WHEN** the matrix is read for TTS models
- **THEN** Chinese-capable models (Cartesia sonic family, `elevenlabs/eleven_flash_v2_5`, `elevenlabs/eleven_turbo_v2_5`, `elevenlabs/eleven_multilingual_v2`, Inworld 1.5 models) include `zh`
- **AND** non-Chinese models (`deepgram/aura-2`, `rime/arcana`, `rime/mistv2`, `elevenlabs/eleven_flash_v2`, `elevenlabs/eleven_turbo_v2`) do not include a Chinese code

#### Scenario: Matrix is mirrored consistently across backend, fallback, and fixture

- **WHEN** the contract tests run
- **THEN** the backend catalog endpoint, the frontend `FALLBACK_MODEL_CATALOG`, and the shared fixture expose the same matrix structure, and any drift fails a test

### Requirement: Language codes are BCP-47 and advisory

The matrix SHALL use BCP-47 language codes (for example `zh-TW`, `zh-Hant`, `zh-CN`, `en-US`). The matrix SHALL be advisory: it informs the editor's offered list and unsupported-combination warnings, but SHALL NOT be used to reject a profile at save time. The save-time validator SHALL continue to guarantee spec shape only, not language runnability, preserving a free-text escape hatch for codes the matrix has not enumerated.

#### Scenario: Unenumerated language code is not rejected

- **WHEN** a profile sets a `language` code that is not present in the matrix for the selected model
- **THEN** the save-time validator does not reject the profile on language grounds
- **AND** the runtime passes the code through to the gateway unchanged
