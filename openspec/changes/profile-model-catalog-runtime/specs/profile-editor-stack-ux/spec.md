## MODIFIED Requirements

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

### Requirement: Voice settings panel

The editor SHALL provide voice settings bound to the correct `models` field per engine mode: in Realtime mode the voice is the `models.realtime.voice` field, and in Pipeline mode the voice is a **separate `models.tts.voice` field**, distinct from the TTS model id, consistent with the LiveKit Inference TTS contract (`model` + separate `voice`). The spec SHALL map each voice control to its exact `models.*` path per mode. For pipeline TTS the editor SHALL present a per-provider suggested-voice selection (from the catalog's suggested-voice list) plus a free-form entry for custom or cloned voice ids. For realtime the voice remains a free-form input (optionally with suggestions). Speed/language controls are OUT OF SCOPE for this change (no per-provider capability matrix exists in the catalog, and no such control exists in the current UI). When they are added in a follow-up, they SHALL be shown only for providers/modes that support them (backed by a catalog capability flag), hidden or disabled otherwise; until then no ignored speed/language value is written. A profile that previously encoded a voice inside the pipeline TTS model id SHALL keep working (the id stays a valid model string) and the editor SHALL surface it without destructively rewriting it, letting the user re-pick into `models.tts.voice`.

#### Scenario: Select a realtime voice

- **WHEN** the user sets the voice in Realtime mode
- **THEN** the value is written to `models.realtime.voice` and round-trips through save/load

#### Scenario: Pipeline voice is a separate field

- **WHEN** the user picks a pipeline TTS voice from the suggested list (or enters a custom id)
- **THEN** the value is written to `models.tts.voice` (separate from `models.tts.model`) and round-trips through save/load, and the runtime applies it as the TTS voice parameter

#### Scenario: Legacy model-id-encoded voice still works

- **WHEN** a profile has a pipeline TTS voice encoded in the model id (the v1 stopgap shape)
- **THEN** the editor displays it without rewriting it, the session still runs, and the user MAY re-pick into the `models.tts.voice` field

#### Scenario: Unsupported control is hidden or disabled

- **WHEN** the active provider/mode does not support a speed (or language) control
- **THEN** that control is hidden or disabled rather than writing an ignored value

## ADDED Requirements

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
