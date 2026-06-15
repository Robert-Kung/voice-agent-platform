## ADDED Requirements

### Requirement: Optional graph block in profile config

Profile config SHALL support an optional `graph` block alongside the existing `instructions`, `tools`, and `human_operator` fields. The `graph` block SHALL contain `schema_version` (integer, `1` for this capability), `global_prompt` (string), `nodes` (array), and `edges` (array). When `graph` is absent, the profile SHALL behave exactly as before (single `instructions` string). Adding the `graph` block SHALL NOT require any database migration, because profile config is persisted as a free-form JSON document.

#### Scenario: Profile without graph block is unchanged

- **WHEN** a profile config has no `graph` key
- **THEN** the system treats it as a single-`instructions` profile and all existing behavior is preserved

#### Scenario: Profile with graph block is accepted and persisted

- **WHEN** a profile config containing a `graph` block with `schema_version`, `global_prompt`, `nodes`, and `edges` is saved
- **THEN** the API stores it in `config_json` without schema migration and returns it intact on read

#### Scenario: Schema version present for future evolution

- **WHEN** a `graph` block is created by the editor
- **THEN** it carries `schema_version: 1`, so future schema revisions can migrate deterministically instead of heuristically

### Requirement: Editor mode flag is the sole strategy-source switch

Profile config SHALL support an optional `editor_mode` field with values `prompt` or `graph`. When absent, `editor_mode` SHALL default to `prompt`. `editor_mode` SHALL be the single source of truth for which strategy representation drives the profile: the graph SHALL drive the conversation strategy if and only if `editor_mode` is `graph` AND the graph passes structural validation. The mere presence of a `graph` block SHALL NOT make it authoritative. When `editor_mode` is `graph` but the graph block is missing or structurally invalid, the system SHALL fall back to the `instructions` string and emit a warning log; it SHALL NOT fail the session (a broken conversation strategy has no FallbackAdapter-style net — the only net is `instructions`).

#### Scenario: Default editor mode

- **WHEN** a profile has no `editor_mode` field
- **THEN** the system treats it as `prompt` mode

#### Scenario: Graph mode declared and valid

- **WHEN** a profile has `editor_mode: graph` and a structurally valid `graph` block
- **THEN** the graph representation is treated as the authoritative conversation strategy for that profile

#### Scenario: Graph block present but prompt mode selected

- **WHEN** a profile has a populated `graph` block and `editor_mode: prompt` (e.g. after reverting a conversion)
- **THEN** the `instructions` string drives the profile and the graph block is retained but not used

#### Scenario: Graph mode with missing or invalid graph falls back

- **WHEN** a profile has `editor_mode: graph` but the `graph` block is absent or fails structural validation
- **THEN** the system falls back to the `instructions` string, logs a warning, and the call proceeds (no hard failure audible to the caller)

### Requirement: Node schema

Each node in `graph.nodes` SHALL have: `id` (stable unique string), `type` (one of `start`, `prompt`, `end`, `handoff`), `title` (display string), `prompt` (focused instruction string; MAY be empty for `end`; for `handoff` it serves as that handoff's greeting/instructions, so multiple handoff nodes with distinct scripts are expressible), `tools` (array of tool names referencing the profile's tool namespace), and `position` (`{x, y}` canvas coordinates). A graph SHALL contain exactly one node of type `start`. The schema SHALL NOT include a `variable_keys` field in version 1: a field with no defined semantics is a contract liability — it would force the future executor to honor arbitrary user-entered strings; data-collection variables are deferred until the executor defines their semantics, to be added with a `schema_version` bump.

#### Scenario: Valid node with all fields

- **WHEN** a node declares `id`, `type`, `title`, `prompt`, `tools`, and `position`
- **THEN** the node is accepted as well-formed

#### Scenario: Exactly one start node

- **WHEN** a graph contains zero or more than one node of type `start`
- **THEN** the graph is flagged invalid (missing or duplicate entry point)

#### Scenario: Node tools reference the profile tool namespace

- **WHEN** a node's `tools` array lists a tool name
- **THEN** that name SHALL refer to a tool defined in the profile's global `tools` list, a built-in tool, or an auto-mounted tool (`lookup_qa`, `transfer_to_human`), and the node does NOT redefine the tool's endpoint or parameters

### Requirement: Edge schema with trigger semantics

Each edge in `graph.edges` SHALL have: `id` (unique string), `source` (a node id), `target` (a node id), `trigger` (one of `user_turn`, `tool_result`; defaults to `user_turn` when absent), `condition` (natural-language string describing when to transition; an empty string SHALL mean an unconditional transition), and `label` (optional short display string). `user_turn` edges are evaluated after a user turn; `tool_result` edges fire on a tool invocation's outcome on the source node (e.g. the elevator flow's "工具回傳後立即轉接" / "建單失敗立即轉接" rules, which cannot be expressed as user-turn conditions). When multiple edges from one source match, priority SHALL be the array order of `edges` (first match wins). No edge SHALL target the `start` node, and no edge SHALL originate from an `end` node. The `condition` string SHALL be treated as design-time text only; its semantic evaluation is out of scope for this capability.

#### Scenario: Conditional user-turn edge

- **WHEN** an edge has `trigger: user_turn` and a non-empty `condition`
- **THEN** the edge represents a transition that applies when that natural-language condition holds after a user turn

#### Scenario: Tool-result edge

- **WHEN** an edge has `trigger: tool_result`
- **THEN** the edge represents a transition fired by the outcome of a tool call on the source node, not by user speech

#### Scenario: Unconditional edge

- **WHEN** an edge has an empty `condition`
- **THEN** the edge represents an unconditional transition from source to target, subject to array-order priority

#### Scenario: Edge endpoints reference existing nodes and respect direction rules

- **WHEN** an edge's `source` or `target` does not match any node `id`, or its target is the `start` node, or its source is an `end` node
- **THEN** the edge is flagged invalid

### Requirement: Single-instructions profile maps to single-node graph

The system SHALL define an equivalence: a profile with only an `instructions` string is equivalent to a graph with one `start` node whose `prompt` equals that `instructions` and whose `tools` equal the profile's global tools. The "lossless and reversible" property SHALL be understood as holding at conversion instant only — after subsequent graph editing, reverting to prompt mode yields the latest flattened representation (see fallback regeneration), not the pre-conversion original, and the UI SHALL NOT claim otherwise.

#### Scenario: Convert single-instructions profile to graph

- **WHEN** a single-`instructions` profile is converted to graph form
- **THEN** a `start` node is created with `prompt` set to the original `instructions` and `tools` set to the profile's global tool names

#### Scenario: Handoff included in conversion

- **WHEN** the source profile has `human_operator.enabled: true`
- **THEN** the conversion adds a `handoff` node and an edge from `start` with a condition describing transfer-to-human

#### Scenario: Reverting to prompt mode

- **WHEN** a converted profile's `editor_mode` is set back to `prompt`
- **THEN** the system uses the current `instructions` field (the latest auto-regenerated flatten) and the graph block is ignored

### Requirement: Fallback instructions are regenerated on every graph save

While a profile is in `graph` mode, every save SHALL regenerate the top-level `instructions` field by flattening the graph (`graphToPrompt`: structured serialization of `global_prompt`, node titles/prompts, and edge trigger/condition descriptions). A frozen, conversion-time fallback is a silent production landmine: SIP calls are pinned to a profile via the `AGENT_PROFILE` secret with no UI banner visible anywhere, so a stale fallback would answer calls with a months-old prompt and zero signal. Regeneration keeps the degraded-execution path (used until `graph-runtime-executor` lands, and as the permanent safety net thereafter) in sync with the current design.

#### Scenario: Save in graph mode refreshes the fallback

- **WHEN** a graph-mode profile is saved after graph edits
- **THEN** the `instructions` field equals the flatten of the saved graph, not the value frozen at conversion time

#### Scenario: SIP call before executor lands

- **WHEN** a SIP call reaches a graph-mode profile while graph execution is not yet available
- **THEN** the agent runs the up-to-date flattened `instructions`, reflecting the current graph design

### Requirement: Runtime execution boundary

This capability SHALL define only the design-time data model. The runtime execution of the graph SHALL be out of scope and is owned by the **`graph-runtime-executor`** change (not `multi-model-runtime`, whose scope is model-provider resolution). The `graph` data model SHALL serve as the frozen contract interface between the three changes. The following execution-relevant facts SHALL be recorded for the executor: (a) graph execution v1 targets **pipeline mode only** — realtime's `TextInputRealtimeModel` binds instructions at Gemini Live connection time, and per-node prompt swapping has unverified latency cost, so realtime graph execution requires a spike before being promised; (b) QA-inline and services-hours content is injected at the global level (composed with `global_prompt`), not per node; (c) a `handoff` node's activation means invoking `transfer_to_human`, and `transfer_to_human` is not unconditionally globally mounted in graph mode; (d) the authoritative structural validator for the runtime gate is a backend (Python) validator owned by `graph-runtime-executor` — the frontend `validateGraph` is UX feedback only, since direct API writes can bypass it.

#### Scenario: Schema is consumable without a runtime

- **WHEN** the `graph` block is defined and stored
- **THEN** no runtime execution semantics are assumed or required by this capability, and the stored structure (including `schema_version` and edge `trigger`) is sufficient for the executor to consume

#### Scenario: Graph profile under realtime mode before executor support

- **WHEN** a graph-mode profile is run under realtime mode
- **THEN** the regenerated `instructions` fallback drives the session (graph execution v1 is pipeline-only)
