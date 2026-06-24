## MODIFIED Requirements

### Requirement: Optional profile models block

A profile config MAY include a `models` block declaring `mode`, `llm`, `stt`, `tts`, and `realtime` settings. The `tts` spec MAY include a `voice` field separate from its `model` id (the LiveKit Inference TTS voice parameter), and any LLM/STT/TTS spec MAY set `via: direct` for a provider with a wired direct build path (e.g. Google LLM with `GOOGLE_API_KEY`). When the `models` block or any of its sub-fields (including `tts.voice`) is absent, the runtime SHALL fall back to the existing built-in defaults, leaving current profile behavior unchanged. The import-light validator SHALL accept these fields when well-formed and reject any `via: direct` combination the runtime cannot build (per the `(kind, provider)` direct-buildable matrix). The validator guarantees spec **shape**, not model-id **runnability**: a free-form/custom model id is NOT validated against the catalog (that would break the custom/cloned-id escape hatch), so an unrunnable pinned id is caught by the runtime preflight fallback (degrade to the safe chain with a warning), not at save time. The validator SHALL also reserve `voice` among the options keys it rejects, so a hand-edited `options.voice` does not collide with the explicit `voice` kwarg at build.

#### Scenario: Profile without models block keeps current behavior
- **WHEN** a profile has no `models` block
- **THEN** the session is built with the existing hard-coded defaults (realtime Gemini Live + Deepgram STT, or pipeline fallback lists) identical to pre-change behavior

#### Scenario: Profile pins a pipeline LLM
- **WHEN** a profile's `models` block sets `mode: pipeline` and an LLM list
- **THEN** the pipeline session uses exactly the declared LLM specs instead of the built-in default list

#### Scenario: Partial models block backfills missing components
- **WHEN** a profile's `models` block declares `llm` but omits `stt` and `tts`
- **THEN** the declared LLM is used and STT/TTS fall back to built-in defaults

#### Scenario: TTS voice field is recognized and validated
- **WHEN** a profile's `models.tts` declares a separate `voice` field
- **THEN** the validator accepts the well-formed spec and the resolved session applies that voice (absent `voice` falls back to prior model-id behavior)

#### Scenario: Google direct LLM spec is accepted
- **WHEN** a profile's `models.llm` declares `provider: google, via: direct`
- **THEN** the validator accepts it (a buildable direct combination) and the runtime uses the Google SDK path
