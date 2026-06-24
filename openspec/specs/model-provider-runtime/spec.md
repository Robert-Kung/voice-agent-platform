# model-provider-runtime Specification

## Purpose

Resolve declarative model specs (`{provider, model, via, options}`) into concrete LiveKit LLM / STT / TTS components in `agents/runtime/providers.py`, including fallback chain assembly, Inference-gateway vs direct-SDK routing, and preservation of the realtime `TextInputRealtimeModel` latency mitigation.
## Requirements
### Requirement: Declarative model spec resolution

The runtime SHALL resolve a declarative model spec of the form `{provider, model, via, options}` into a concrete LiveKit component (`llm.LLM`, `stt.STT`, or `tts.TTS`) in `agents/runtime/providers.py`, without hard-coded provider branching in `agent.py`. The first implementation SHALL route `via: inference` specs through the LiveKit Inference gateway as a `{provider}/{model}` string and special-case only the `via: direct` providers actually in use (`deepgram` STT, `google` realtime); a full provider registry is deferred until graph-agent-builder requires per-node arbitrary providers.

#### Scenario: Resolve an Inference-gateway LLM spec
- **WHEN** a spec `{kind: llm, provider: google, model: gemini-3.1-flash-lite, via: inference}` is resolved
- **THEN** the resolver returns an `inference.LLM` instance configured for `google/gemini-3.1-flash-lite`

#### Scenario: Resolve a direct-SDK STT spec
- **WHEN** a spec `{kind: stt, provider: deepgram, model: nova-2, via: direct, language: zh-TW}` is resolved
- **THEN** the resolver returns a `deepgram.STT` instance using the Deepgram API key from the environment

#### Scenario: Unknown provider fails loud
- **WHEN** a spec names a provider/via combination absent from the registry
- **THEN** the resolver raises an explicit error naming the unsupported provider rather than silently substituting a default

### Requirement: Fallback chain assembly

The runtime SHALL assemble an ordered list of model specs into a LiveKit `FallbackAdapter`, with the first spec as primary and subsequent specs as fallbacks. A single-element list SHALL produce a bare component without an adapter wrapper.

#### Scenario: Multiple specs become a FallbackAdapter
- **WHEN** an LLM list contains a primary `google/gemini-3.1-flash-lite` and a fallback `openai/gpt-4.1-mini`
- **THEN** the resolver returns an `llm.FallbackAdapter` whose first entry is the Gemini model and second entry is the OpenAI model

#### Scenario: Single spec produces no adapter
- **WHEN** an STT list contains exactly one spec
- **THEN** the resolver returns the bare `stt.STT` instance without wrapping it in a `FallbackAdapter`

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

### Requirement: Realtime mode preserves TextInputRealtimeModel latency mitigation

When the agent mode is `realtime`, the runtime SHALL build the LLM as a `TextInputRealtimeModel` wrapping Google Gemini Live, and SHALL force the latency-mitigation settings (`push_audio` no-op, `start_user_activity` no-op, `automatic_activity_detection.disabled=True`, `input_audio_transcription=None`). These settings SHALL NOT be overridable by profile config.

#### Scenario: Realtime LLM is always TextInputRealtimeModel
- **WHEN** mode is `realtime` and the profile selects a Gemini Live model and voice
- **THEN** the LLM component is a `TextInputRealtimeModel` configured with that model and voice, with audio-push interception active

#### Scenario: Non-Gemini realtime provider is rejected
- **WHEN** mode is `realtime` and the profile's realtime spec names a non-Gemini provider
- **THEN** the runtime raises an explicit error rather than attempting an unsupported full-duplex realtime model

#### Scenario: Realtime STT remains multi-provider
- **WHEN** mode is `realtime` and the profile specifies a realtime STT spec
- **THEN** the runtime resolves that STT spec normally as the text-input source feeding Gemini Live

### Requirement: Pipeline TTS applies an explicit voice parameter

The pipeline TTS build SHALL pass an explicit voice parameter to the TTS component when `models.tts.voice` is present, consistent with the LiveKit Inference TTS contract where the voice is a separate parameter from the model id. When `models.tts.voice` is absent, the build SHALL preserve current behavior (model-id-only, with any voice encoded in the model id still honored by the gateway). The voice parameter SHALL NOT be silently dropped.

#### Scenario: Voice field applied at build
- **WHEN** a profile's `models.tts` declares both a `model` and a `voice`
- **THEN** the resolved TTS component is built with that voice as its voice parameter

#### Scenario: Absent voice preserves prior behavior
- **WHEN** a profile's `models.tts` declares a `model` but no `voice`
- **THEN** the TTS component is built from the model id alone, identical to pre-change behavior

