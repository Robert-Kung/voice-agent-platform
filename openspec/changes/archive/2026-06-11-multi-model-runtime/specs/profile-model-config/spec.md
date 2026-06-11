## ADDED Requirements

### Requirement: Optional profile models block

A profile config MAY include a `models` block declaring `mode`, `llm`, `stt`, `tts`, and `realtime` settings. When the `models` block or any of its sub-fields is absent, the runtime SHALL fall back to the existing built-in defaults, leaving current profile behavior unchanged.

#### Scenario: Profile without models block keeps current behavior
- **WHEN** a profile has no `models` block
- **THEN** the session is built with the existing hard-coded defaults (realtime Gemini Live + Deepgram STT, or pipeline fallback lists) identical to pre-change behavior

#### Scenario: Profile pins a pipeline LLM
- **WHEN** a profile's `models` block sets `mode: pipeline` and an LLM list
- **THEN** the pipeline session uses exactly the declared LLM specs instead of the built-in default list

#### Scenario: Partial models block backfills missing components
- **WHEN** a profile's `models` block declares `llm` but omits `stt` and `tts`
- **THEN** the declared LLM is used and STT/TTS fall back to built-in defaults

### Requirement: Mode selection and env override

The runtime SHALL determine the agent mode from `models.mode` in the profile, with the `AGENT_MODE` environment variable taking precedence when set. When neither is present, the runtime SHALL use the existing default mode.

#### Scenario: AGENT_MODE env overrides profile mode
- **WHEN** a profile declares `models.mode: pipeline` and `AGENT_MODE=realtime` is set in the environment
- **THEN** the session is built in realtime mode

#### Scenario: Profile mode used when env unset
- **WHEN** a profile declares `models.mode: pipeline` and `AGENT_MODE` is unset
- **THEN** the session is built in pipeline mode

### Requirement: Model config flows through multi-process and SIP paths

Model settings SHALL travel with the profile config (DB or YAML), so that a forked child process re-loading the profile and a SIP call pinned to `AGENT_PROFILE` both receive the correct model selection without relying on `sys.argv`.

#### Scenario: Forked child process gets model config
- **WHEN** the LiveKit worker forks a child process to run `entrypoint()` and that child re-loads the active profile
- **THEN** the child resolves the same `models` block as declared in the profile, without needing the parent's command-line `--profile` flag

#### Scenario: SIP call inherits profile model config
- **WHEN** a SIP call is dispatched with the profile fixed by the `AGENT_PROFILE` secret
- **THEN** the session uses that profile's `models` block, requiring no code change to select models per phone number
