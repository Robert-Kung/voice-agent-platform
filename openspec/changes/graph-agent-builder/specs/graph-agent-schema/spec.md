## ADDED Requirements

### Requirement: Optional graph block in profile config

Profile config SHALL support an optional `graph` block alongside the existing `instructions`, `tools`, and `human_operator` fields. The `graph` block SHALL contain `global_prompt` (string), `nodes` (array), and `edges` (array). When `graph` is absent, the profile SHALL behave exactly as before (single `instructions` string). Adding the `graph` block SHALL NOT require any database migration, because profile config is persisted as a free-form JSON document.

#### Scenario: Profile without graph block is unchanged

- **WHEN** a profile config has no `graph` key
- **THEN** the system treats it as a single-`instructions` profile and all existing behavior is preserved

#### Scenario: Profile with graph block is accepted and persisted

- **WHEN** a profile config containing a `graph` block with `global_prompt`, `nodes`, and `edges` is saved
- **THEN** the API stores it in `config_json` without schema migration and returns it intact on read

### Requirement: Editor mode flag

Profile config SHALL support an optional `editor_mode` field with values `prompt` or `graph`. When absent, `editor_mode` SHALL default to `prompt`. The flag SHALL determine which editor view is opened by default and SHALL act as the single source of truth for which strategy representation drives the profile.

#### Scenario: Default editor mode

- **WHEN** a profile has no `editor_mode` field
- **THEN** the system treats it as `prompt` mode

#### Scenario: Graph mode declared

- **WHEN** a profile has `editor_mode: graph` and a populated `graph` block
- **THEN** the graph representation is treated as the authoritative conversation strategy for that profile

### Requirement: Node schema

Each node in `graph.nodes` SHALL have: `id` (stable unique string), `type` (one of `start`, `prompt`, `end`, `handoff`), `title` (display string), `prompt` (focused instruction string; MAY be empty for `end`), `tools` (array of tool names referencing the profile's tool namespace), `variable_keys` (array of variable name strings), and `position` (`{x, y}` canvas coordinates). A graph SHALL contain exactly one node of type `start`.

#### Scenario: Valid node with all fields

- **WHEN** a node declares `id`, `type`, `title`, `prompt`, `tools`, `variable_keys`, and `position`
- **THEN** the node is accepted as well-formed

#### Scenario: Exactly one start node

- **WHEN** a graph contains zero or more than one node of type `start`
- **THEN** the graph is flagged invalid (missing or duplicate entry point)

#### Scenario: Node tools reference the profile tool namespace

- **WHEN** a node's `tools` array lists a tool name
- **THEN** that name SHALL refer to a tool defined in the profile's global `tools` list (or a built-in tool), and the node does NOT redefine the tool's endpoint or parameters

### Requirement: Edge schema

Each edge in `graph.edges` SHALL have: `id` (unique string), `source` (a node id), `target` (a node id), `condition` (natural-language string describing when to transition; an empty string SHALL mean an unconditional transition), and `label` (optional short display string). The `condition` string SHALL be treated as design-time text only; its semantic evaluation is out of scope for this capability.

#### Scenario: Conditional edge

- **WHEN** an edge has a non-empty `condition`
- **THEN** the edge represents a transition that applies when that natural-language condition holds

#### Scenario: Unconditional edge

- **WHEN** an edge has an empty `condition`
- **THEN** the edge represents an unconditional transition from source to target

#### Scenario: Edge endpoints reference existing nodes

- **WHEN** an edge's `source` or `target` does not match any node `id`
- **THEN** the edge is flagged invalid

### Requirement: Single-instructions profile maps to single-node graph

The system SHALL define a lossless equivalence: a profile with only an `instructions` string is equivalent to a graph with one `start` node whose `prompt` equals that `instructions` and whose `tools` equal the profile's global tools. Converting a single-`instructions` profile to graph form SHALL preserve the original `instructions` field unchanged so the conversion is reversible.

#### Scenario: Convert single-instructions profile to graph

- **WHEN** a single-`instructions` profile is converted to graph form
- **THEN** a `start` node is created with `prompt` set to the original `instructions` and `tools` set to the profile's global tool names, and the original `instructions` field is left intact

#### Scenario: Handoff included in conversion

- **WHEN** the source profile has `human_operator.enabled: true`
- **THEN** the conversion adds a `handoff` node and an edge from `start` with a condition describing transfer-to-human

#### Scenario: Reverting to prompt mode

- **WHEN** a converted profile's `editor_mode` is set back to `prompt`
- **THEN** the system uses the preserved `instructions` field and the graph block is ignored

### Requirement: Runtime execution boundary

This capability SHALL define only the design-time data model. The runtime execution of the graph (state machine, per-turn edge condition evaluation, node transitions, how `global_prompt` is composed into LLM calls) SHALL be out of scope and is owned by the `multi-model-runtime` change. The `graph` data model SHALL serve as the contract interface between the two changes.

#### Scenario: Schema is consumable without a runtime

- **WHEN** the `graph` block is defined and stored
- **THEN** no runtime execution semantics are assumed or required by this capability, and the stored structure is sufficient for a future runtime to consume
