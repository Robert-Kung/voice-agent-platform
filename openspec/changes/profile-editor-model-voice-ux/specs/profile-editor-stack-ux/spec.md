## ADDED Requirements

### Requirement: Global-as-base-layer editor information architecture

The profile editor SHALL present global configuration (`global_prompt`, persona/identity, QA, service hours, global tools, and the model/voice stack) as an **always-on base layer that applies to the whole agent in both `prompt` and `graph` modes**, and SHALL present the graph as an **optional branching layer layered on top of global** rather than an alternative to it. This framing SHALL be carried by a concrete layout affordance (e.g. a persistent labeled "global / applies everywhere" container, or the graph canvas rendered inside a labeled "branching layer" frame), **not by copy alone**, so the layout does not visually teach the opposite. The model/voice stack settings SHALL be reachable from the header Stack summary chip (click-to-open panel/popover) so the highest-stakes settings are not demoted to a low-discoverability collapsed accordion slot. Global configuration SHALL be preserved unchanged across `prompt`↔`graph` conversion and revert.

#### Scenario: Global config presented as always-on base layer

- **WHEN** the user views the editor in either `prompt` or `graph` mode
- **THEN** the global settings (global prompt, identity, QA, hours, global tools, model/voice stack) are presented via a persistent layout affordance as applying to the whole agent regardless of mode, and the graph is presented as an optional branching layer on top — not as a replacement for global

#### Scenario: Stack reachable from header chip

- **WHEN** the user clicks the header Stack summary chip
- **THEN** the model/voice stack settings open directly (panel/popover), without hunting through collapsed right-panel accordion sections

#### Scenario: Global config survives mode conversion

- **WHEN** the user converts a profile to graph mode and later reverts to prompt mode
- **THEN** the global configuration (global prompt, identity, QA, hours, global tools, model/voice stack) is unchanged by the conversion and revert

### Requirement: Engine-mode model selection UI

The profile editor SHALL provide a model-stack settings UI that reads and writes the profile config's existing `models` block (`mode`, `llm`, `stt`, `tts`, `realtime`) with no DB migration. The UI SHALL conform to the existing backend `models`-block validation contract; making the UI work SHALL require **zero backend runtime changes**. A read-only backend endpoint that exposes the compiled default model names and the legal provider/model/variant lists for the UI to consume is permitted (and recommended over hardcoding) because it adds no runtime behavior — see the model-list source-of-truth requirement.

The UI SHALL present the engine mode as two tabs — **Realtime (Speech-to-Speech)** and **Pipeline** — where the selected tab sets `models.mode` (`realtime` | `pipeline`). The Realtime tab SHALL expose the realtime model/voice/thinking fields (`models.realtime`); the Pipeline tab SHALL expose separate STT, TTS, and LLM provider+model selectors (`models.stt` / `models.tts` / `models.llm`). Switching tabs SHALL NOT clear the inactive mode's `models` sub-block (keep-but-don't-clear), so toggling between modes is non-destructive. When the `models` block or a sub-field is absent, the UI SHALL show the **compiled built-in default** as the inherited value rather than forcing the user to pick, and SHALL NOT write that value into config (preserving unchanged-by-default behavior). The UI SHALL visually distinguish an **inherited default** (tracks future built-in changes) from a **pinned** value, and SHALL note that a deployment-layer env override (e.g. `GOOGLE_REALTIME_MODEL` / `GOOGLE_REALTIME_VOICE`) can shadow the displayed default — i.e. the shown value is the compiled default, not a guaranteed runtime-effective value.

#### Scenario: Switch engine mode via tabs

- **WHEN** the user selects the Realtime or Pipeline tab
- **THEN** `models.mode` is set accordingly and the tab shows the fields relevant to that mode (realtime model/voice vs pipeline STT/TTS/LLM)

#### Scenario: Pin a pipeline LLM from the UI

- **WHEN** the user, on the Pipeline tab, selects an LLM provider and model
- **THEN** the choice is written into `models.llm` in the profile config and round-trips through save/load intact

#### Scenario: Absent models block shows compiled default, marked inherited

- **WHEN** a profile has no `models` block or omits a sub-field
- **THEN** the UI displays the compiled built-in default for that slot marked as "inherited" (not pinned), does not write an explicit value, and indicates a deployment env override may shadow it — leaving behavior unchanged on save

#### Scenario: Switching engine tabs is non-destructive

- **WHEN** the user switches from Pipeline to Realtime and back
- **THEN** both `models.realtime` and `models.stt`/`tts`/`llm` sub-blocks are preserved (the inactive mode's pinned values are not cleared), and only `models.mode` reflects the active tab

### Requirement: Engine-mode change is a strategy change requiring confirmation

Because `models.mode` selects the runtime engine (cost profile, latency profile, and whether a graph executes natively), changing the engine mode SHALL be treated as a runtime-strategy change on save, consistent with the `editor_mode` switch. Saving a profile whose `models.mode` changed since load SHALL require an explicit confirmation stating that the save changes the live runtime engine. This confirmation SHALL reuse the existing `editor_mode` save-confirmation surface (the `SaveConfirmModal`): when both `editor_mode` and `models.mode` changed in one save, the editor SHALL present a SINGLE combined confirmation listing both strategy changes, not two stacked dialogs.

#### Scenario: Mode change requires save confirmation

- **WHEN** the user changes the engine mode tab and saves
- **THEN** a confirmation is shown stating the save changes the live runtime engine (cost/latency/graph-execution), and the save proceeds only on confirm

#### Scenario: Combined confirmation when both strategy switches changed

- **WHEN** the user has changed both `editor_mode` and `models.mode` since load and saves
- **THEN** a single confirmation is shown that lists both the strategy-source change (`editor_mode`) and the engine change (`models.mode`), and the save proceeds only on confirm — the user is not asked to confirm twice

### Requirement: Model-list and default source of truth

The UI's legal provider/model/variant lists and the displayed compiled defaults SHALL derive from a single source of truth aligned with the backend (`KNOWN_DIRECT_PROVIDERS`, the realtime Gemini Live variant allowlist, and the compiled pipeline defaults). If the UI hardcodes these lists rather than consuming a backend endpoint, a contract test SHALL assert the hardcoded set matches a fixture mirroring the backend constants, so the two cannot drift silently — the same parity discipline this change applies to the graph validator.

#### Scenario: Hardcoded lists guarded against drift

- **WHEN** the frontend model/variant lists are hardcoded
- **THEN** a unit test fails if they diverge from a fixture mirroring the backend's authoritative constants (`KNOWN_DIRECT_PROVIDERS` / realtime variant allowlist)

#### Scenario: Realtime variant allowlist stays in sync with cost

- **WHEN** a new realtime Gemini Live variant is offered in the UI
- **THEN** it is present in the backend allowlist and has a corresponding cost rate, preventing the UI from offering a variant the runtime rejects or misprices

### Requirement: Realtime constraint feedback

The Realtime tab SHALL communicate the realtime-mode constraints inline: the realtime LLM is restricted to the wrapped Gemini Live model (the `TextInputRealtimeModel` latency-mitigation design — intercept `push_audio` → Deepgram STT → text into Gemini), and known-dead Gemini Live variants are not selectable. The UI SHALL NOT offer non-Gemini realtime LLM providers.

#### Scenario: Realtime restricts LLM to Gemini Live

- **WHEN** the user is on the Realtime tab
- **THEN** the LLM selection is constrained to the supported Gemini Live variant(s) and non-Gemini realtime providers are not offered, with the constraint explained inline

#### Scenario: Realtime STT remains selectable

- **WHEN** the user is on the Realtime tab
- **THEN** the STT provider (text-input source feeding Gemini) is selectable, consistent with the realtime signal flow, without exposing a non-Gemini realtime LLM

### Requirement: Graph and realtime exclusivity feedback

When a profile is in `editor_mode: graph`, the editor SHALL communicate that graph execution runs only in pipeline mode and SHALL prevent or clearly warn against pairing it with `models.mode: realtime` before save. The backend remains the authoritative gate (save returns 422 for `editor_mode: graph` + `models.mode: realtime`); the UI SHALL surface this constraint proactively rather than only surfacing the backend rejection.

This requirement is the authoritative owner of the in-editor graph×realtime messaging: when a graph profile has `models.mode: realtime` selected in the editor, the editor SHALL show this exclusivity warning (the combination is unsavable) and SHALL NOT show the `graph-editor-ux` "Deployment-aware execution status" degradation framing — that framing is reserved for describing the deployment-layer `AGENT_MODE` env override of an already-saved (pipeline-declared) graph profile.

#### Scenario: Graph profile warns on realtime mode selection

- **WHEN** a profile in `editor_mode: graph` has the Realtime tab selected (`models.mode: realtime`)
- **THEN** the editor surfaces a blocking-intent warning that graph execution requires pipeline deployment and that saving this combination will be rejected by the backend

#### Scenario: Backend rejection surfaced clearly

- **WHEN** the user saves a `editor_mode: graph` + `models.mode: realtime` combination and the backend returns 422
- **THEN** the editor presents the rejection as the graph×realtime exclusivity constraint, not a generic save error

### Requirement: Voice settings panel

The editor SHALL provide voice settings bound to the correct `models` field per engine mode: in Realtime mode the voice is the `models.realtime.voice` field, and in Pipeline mode the voice is carried by the TTS selection (`models.tts`, where many providers encode the voice in the `model` field). The spec SHALL map each voice control to its exact `models.*` path per mode rather than leaving it generic. Because no curated voice catalog exists in the codebase today (realtime voice is a free-form string, pipeline TTS voices are encoded in the model id), v1 SHALL provide a free-form voice input (optionally with suggestions) for realtime and the provider/model selector for pipeline TTS. A metadata-rich searchable catalog (language/gender/accent badges) and sample playback are deferred extensions, NOT v1 requirements, and the spec SHALL NOT imply metadata is shown when no catalog source exists. Speed/language controls SHALL be shown only for providers/modes that support them (hidden or disabled otherwise).

#### Scenario: Select a realtime voice

- **WHEN** the user sets the voice in Realtime mode
- **THEN** the value is written to `models.realtime.voice` and round-trips through save/load

#### Scenario: Pipeline voice via TTS selection

- **WHEN** the user picks a pipeline TTS provider/model that encodes a voice
- **THEN** the voice is carried by `models.tts` and round-trips through save/load, without a separate conflicting voice field

#### Scenario: Unsupported control is hidden or disabled

- **WHEN** the active provider/mode does not support a speed (or language) control
- **THEN** that control is hidden or disabled rather than writing an ignored value

### Requirement: Interaction states for new controls

The model/voice UI SHALL specify and handle its interaction states: the realtime LLM constrained/disabled state (non-Gemini not offered, dead variants not selectable), the unsaved/dirty state for new fields (reflected in `isDirty` and surfaced in the existing save affordance), and the surface and copy for a backend save rejection (the graph×realtime 422). If any model/variant list is fetched rather than hardcoded, loading and fetch-error states SHALL be handled rather than rendering an empty picker silently.

#### Scenario: Realtime LLM constrained state is visible

- **WHEN** the user is on the Realtime tab
- **THEN** the LLM control communicates the Gemini-Live-only constraint (offered set limited, with the reason visible) rather than appearing as an unexplained empty/locked control

#### Scenario: Save rejection is surfaced in-context

- **WHEN** a save is rejected by the backend with the graph×realtime 422
- **THEN** the rejection is surfaced near the engine-mode control as the exclusivity constraint, and the unsaved edits are retained

#### Scenario: Dirty state reflects model/voice edits

- **WHEN** the user changes any model or voice field
- **THEN** the editor's unsaved/dirty indicator reflects the change via the existing `isDirty` mechanism
