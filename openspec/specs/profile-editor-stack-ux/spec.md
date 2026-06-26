# profile-editor-stack-ux Specification

## Purpose

Define the profile editor's model/voice stack-authoring experience: a global-as-base-layer information architecture, an engine-mode (Realtime/Pipeline) model selection UI bound to the existing `models` config block with zero backend runtime changes, strategy-change confirmation on engine switches, a single model-list source of truth kept in parity with the backend, realtime-constraint feedback, graph×realtime exclusivity gating, a voice settings panel mapped to exact `models.*` paths, and the interaction states for these new controls.
## Requirements
### Requirement: Global-as-base-layer editor information architecture

The profile editor SHALL present global configuration (`global_prompt`, persona/identity, QA, service hours, global tools, and the model/voice stack) as an **always-on base layer that applies to the whole agent in both `prompt` and `graph` modes**, and SHALL present the graph as an **optional branching layer layered on top of global** rather than an alternative to it. This framing SHALL be carried by a concrete layout affordance (e.g. a persistent labeled "global / applies everywhere" container, or the graph canvas rendered inside a labeled "branching layer" frame), **not by copy alone**, so the layout does not visually teach the opposite. The model/voice stack settings SHALL be reachable from the header Stack summary chip, which SHALL present an explicit editable affordance (distinct from a passive status badge) and on activation SHALL open a **dedicated full-width Model & Voice view** giving the model/voice controls room for a multi-column layout, instead of a constrained center modal — so the highest-stakes settings are neither demoted to a low-discoverability collapsed accordion slot nor cramped into an overflowing modal. The full-width view SHALL preserve the in-progress unsaved draft (it does not unmount the editor form state) and SHALL provide an explicit way back to the editor. Global configuration SHALL be preserved unchanged across `prompt`↔`graph` conversion and revert.

#### Scenario: Global config presented as always-on base layer

- **WHEN** the user views the editor in either `prompt` or `graph` mode
- **THEN** the global settings (global prompt, identity, QA, hours, global tools, model/voice stack) are presented via a persistent layout affordance as applying to the whole agent regardless of mode, and the graph is presented as an optional branching layer on top — not as a replacement for global

#### Scenario: Stack chip opens the full-width Model & Voice view

- **WHEN** the user clicks the header Stack summary chip
- **THEN** the editor swaps to a dedicated full-width Model & Voice view showing the engine-mode selection and the per-component (TTS / LLM / STT) controls in a multi-column layout, without opening a center modal and without hunting through collapsed right-panel accordion sections

#### Scenario: Stack chip reads as editable, not as a status badge

- **WHEN** the user looks at the header
- **THEN** the Stack chip is visually distinguished as an interactive entry point (e.g. accent styling plus a settings affordance and hover state), so it does not read as the passive language/status pill next to it

#### Scenario: Full-width view preserves unsaved edits

- **WHEN** the user has unsaved edits, opens the full-width Model & Voice view, and returns to the editor
- **THEN** all unsaved edits and dirty state are preserved (the view swap does not unmount the editor form)

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

The UI's legal provider/model lists, the realtime variant allowlist, the per-provider suggested-voice lists, and the displayed compiled defaults SHALL derive from a single source of truth aligned with the backend, served by the read-only `GET /api/model-defaults` endpoint, which exposes the curated **LiveKit Inference catalog** (the enumerable provider/model set the gateway accepts) rather than a tiny hardcoded subset. Provider AND model SHALL be presentable as enumerable selections (dropdowns), not requiring hand-typed entry for catalog models; a free-form entry MAY remain as an escape hatch for custom/cloned ids. Each catalog model SHALL carry a flag indicating whether a cost rate exists for it. The frontend offline fallback and the catalog payload SHALL be guarded against drift by a contract test asserting they match a shared fixture mirroring the backend constants, checked from BOTH the backend (pytest) and the frontend (vitest) — the same parity discipline this change applies to the graph validator. Every catalog model-id string SHALL be one verified to be accepted by the live LiveKit Inference gateway (no id is offered that the runtime would reject).

#### Scenario: Provider and model are enumerable from the catalog

- **WHEN** the user selects a pipeline LLM/STT/TTS provider and then a model
- **THEN** both are chosen from the catalog served by the endpoint (dropdowns), and the chosen `provider/model` is one the LiveKit Inference gateway accepts at runtime

#### Scenario: Catalog parity guarded against drift

- **WHEN** the frontend catalog fallback or the backend catalog changes
- **THEN** a contract test fails if the two diverge from the shared backend-constants fixture (checked from both pytest and vitest)

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

Because graph execution runs only in pipeline mode, the editor SHALL gate the engine selection by `editor_mode` rather than letting the user select the invalid combination and only warning afterward. When a profile is in `editor_mode: graph`, the Realtime tab SHALL be presented as disabled/locked with an inline reason (graph execution requires pipeline deployment), so `models.mode: realtime` is not reachable through the UI while graph is active; Pipeline is the only selectable engine. This is **input affordance, not a frontend save-gate** — the backend remains the authoritative gate (save returns 422 for `editor_mode: graph` + `models.mode: realtime`) for any path that bypasses the UI (direct API / YAML), and the frontend SHALL NOT intercept the save to fake-validate.

When the user converts a profile that is currently `models.mode: realtime` to `graph` mode, the editor SHALL surface a confirmation that graph requires pipeline and, on confirm, switch `models.mode` to `pipeline` as part of the conversion, rather than silently producing an unsavable graph+realtime state.

This requirement is the authoritative owner of the in-editor graph×realtime relationship: while `editor_mode: graph`, realtime is gated out (locked tab), and the editor SHALL NOT show the `graph-editor-ux` "Deployment-aware execution status" degradation framing for a graph profile — that framing is reserved for describing the deployment-layer `AGENT_MODE` env override of an already-saved (pipeline-declared) graph profile.

#### Scenario: Realtime tab locked in graph mode

- **WHEN** a profile is in `editor_mode: graph`
- **THEN** the Realtime engine tab is disabled/locked with an inline reason (graph requires pipeline), Pipeline is the only selectable engine, and `models.mode: realtime` cannot be selected through the UI

#### Scenario: Converting a realtime profile to graph switches to pipeline

- **WHEN** the user converts a profile whose `models.mode` is `realtime` to `graph` mode and confirms
- **THEN** `models.mode` is switched to `pipeline` as part of the conversion, so the editor never holds an unsavable `editor_mode: graph` + `models.mode: realtime` state

#### Scenario: Backend rejection surfaced clearly (bypass defense)

- **WHEN** a `editor_mode: graph` + `models.mode: realtime` combination nonetheless reaches save (e.g. via direct API/YAML that bypassed the locked tab) and the backend returns 422
- **THEN** the editor presents the rejection as the graph×realtime exclusivity constraint, not a generic save error, and retains the unsaved edits

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

### Requirement: Provider direct-key toggle

For providers that have a wired direct-SDK build path (Google), the editor SHALL expose a per-spec toggle between `via:inference` (LiveKit gateway, no key) and `via:direct` (provider SDK + key from deployment env, e.g. `GOOGLE_API_KEY`). The toggle SHALL be offered ONLY for providers the runtime can actually build directly; providers without a direct path SHALL NOT present the toggle. Selecting `via:direct` SHALL write `via: "direct"` into the corresponding `models.*` spec and round-trip. This is an input affordance; the backend validator remains the authoritative gate for whether a `via:direct` combination is buildable.

#### Scenario: Direct-key toggle offered only where buildable

- **WHEN** the user views the provider toggle for a Google LLM spec
- **THEN** both `via:inference` and `via:direct` are selectable, while a provider with no direct build path shows no toggle (inference only)

#### Scenario: Direct selection round-trips

- **WHEN** the user sets a Google LLM spec to `via:direct` and saves
- **THEN** `models.llm` records `via: "direct"` and reloads with the direct path selected

### Requirement: Unpriced model selectability and flagging

The editor SHALL allow selecting any model in the catalog, including models with no cost rate in the backend rate tables. A model without a known cost rate SHALL be visibly flagged (e.g. "cost estimate unavailable") at selection time rather than hidden or blocked, so the user understands cost estimation will be incomplete for that choice. Selection and save SHALL proceed normally for such models.

#### Scenario: Unpriced model is selectable and flagged

- **WHEN** the user selects a catalog model that has no cost rate
- **THEN** the model is selectable and saved, and the UI shows a "cost estimate unavailable" indicator rather than hiding or disabling the option

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

