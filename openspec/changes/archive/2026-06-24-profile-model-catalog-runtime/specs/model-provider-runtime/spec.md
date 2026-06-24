## MODIFIED Requirements

### Requirement: Inference gateway and direct SDK coexistence

The runtime SHALL support both `via: inference` (LiveKit Inference gateway) and `via: direct` (provider SDK plugin + provider API key) for the same provider, selectable per spec. The default `via` SHALL be `inference` when unspecified. In addition to the Deepgram-STT direct path, the runtime SHALL provide a **Google direct-SDK build path for the pipeline LLM** (provider plugin + `GOOGLE_API_KEY`), so a `models.llm` spec with `provider: google, via: direct` builds a working pipeline LLM rather than failing. A `via: direct` spec naming a provider with no wired direct build path SHALL fail loud at build time (no silent fallback), and the import-light validator SHALL reject at save time any `via: direct` combination the runtime cannot build.

#### Scenario: Default via is inference
- **WHEN** a spec omits the `via` field
- **THEN** the resolver treats it as `via: inference`

#### Scenario: Global STT provider env override
- **WHEN** the `AGENT_STT_PROVIDER` environment variable is set to `deepgram`
- **THEN** all STT specs resolve via the direct Deepgram SDK regardless of each spec's declared `via`, preserving the Try-button local-test behavior

#### Scenario: Google pipeline LLM via direct SDK
- **WHEN** a profile's `models.llm` spec sets `provider: google, via: direct`
- **THEN** the runtime builds the pipeline LLM through the Google SDK plugin using `GOOGLE_API_KEY`, instead of the Inference gateway

#### Scenario: Unbuildable direct provider fails loud
- **WHEN** a spec sets `via: direct` for a provider with no wired direct build path
- **THEN** the build fails with a clear error (and the save-time validator rejects the same combination), rather than silently falling back to inference

## ADDED Requirements

### Requirement: Pipeline TTS applies an explicit voice parameter

The pipeline TTS build SHALL pass an explicit voice parameter to the TTS component when `models.tts.voice` is present, consistent with the LiveKit Inference TTS contract where the voice is a separate parameter from the model id. When `models.tts.voice` is absent, the build SHALL preserve current behavior (model-id-only, with any voice encoded in the model id still honored by the gateway). The voice parameter SHALL NOT be silently dropped.

#### Scenario: Voice field applied at build
- **WHEN** a profile's `models.tts` declares both a `model` and a `voice`
- **THEN** the resolved TTS component is built with that voice as its voice parameter

#### Scenario: Absent voice preserves prior behavior
- **WHEN** a profile's `models.tts` declares a `model` but no `voice`
- **THEN** the TTS component is built from the model id alone, identical to pre-change behavior
