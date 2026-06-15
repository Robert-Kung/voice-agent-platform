## ADDED Requirements

### Requirement: Editable graph canvas with controlled state ownership

The profile editor SHALL provide an editable graph canvas (built on the existing React Flow `agent-flow-builder` component) in which the user can add nodes, delete nodes, and connect nodes with edges. The canvas SHALL replace the prompt-first center pane when the profile's `editor_mode` is `graph`. The form hook's `known.graph` SHALL be the single source of truth: the canvas SHALL operate as a controlled component deriving nodes/edges from `config.graph`, and SHALL propagate changes upward only on semantic events (connect, node/edge delete, drag-stop, inspector edit) — never per pixel of drag. Node positions changed on the canvas SHALL persist to each node's `position` field on drag-stop. (The pre-existing component initializes internal state from props once and never invokes its declared change callbacks; carrying that pattern into editable mode would silently lose edits on save.)

#### Scenario: Add a node

- **WHEN** the user adds a node of a chosen type (`prompt`, `handoff`, or `end`) on the canvas
- **THEN** a new node with a unique `id` and default fields is created in `known.graph` and rendered

#### Scenario: Connect two nodes

- **WHEN** the user drags from one node's source handle to another node's target handle
- **THEN** a new edge with `source`, `target`, `trigger: user_turn`, and an empty `condition` is created in `known.graph`

#### Scenario: Delete a node

- **WHEN** the user deletes a node
- **THEN** the node and all edges referencing it are removed from `known.graph`

#### Scenario: Canvas edits survive save

- **WHEN** the user connects nodes or moves a node and then saves
- **THEN** the persisted `config.graph` contains those edits (changes reached the form hook, not just canvas-internal state)

#### Scenario: Persisted layout

- **WHEN** the user moves a node and saves
- **THEN** the node's `position` is persisted and restored on next open

### Requirement: Edge trigger and condition editing

The editor SHALL let the user edit each edge's `trigger` (`user_turn` | `tool_result`), natural-language `condition`, and optional `label`. The condition SHALL be presented as free text describing when the conversation transitions along that edge. Edge priority SHALL follow the `edges` array order (first match wins).

#### Scenario: Edit edge condition

- **WHEN** the user selects an edge and enters a natural-language condition
- **THEN** the edge's `condition` field is updated and the edge's `label` (if set) is shown on the canvas

#### Scenario: Mark an edge as tool-result triggered

- **WHEN** the user sets an edge's trigger to `tool_result`
- **THEN** the edge's `trigger` field is updated, expressing a transition fired by a tool outcome (e.g. ticket created / ticket failed) rather than user speech

### Requirement: Node inspector side panel

When a node is selected, the right panel SHALL switch to a Node Inspector showing that node's `title`, `prompt`, and `tools` for editing. The tools editor within the inspector SHALL reuse the existing tools UI and reference the profile's global tool list rather than redefining tools. When the selected node is the `start` node, the inspector SHALL additionally project the top-level `welcome_message` and `welcome_instructions` fields for editing (data remains top-level; without this projection, graph mode would have no UI to edit the fields that drive the runtime greeting, since their only editor lives in the prompt-mode-only center pane).

#### Scenario: Edit node prompt

- **WHEN** the user selects a node and edits its prompt in the inspector
- **THEN** the node's `prompt` field is updated

#### Scenario: Attach a tool to a node

- **WHEN** the user attaches a tool to the selected node
- **THEN** the tool's name is added to the node's `tools` array, referencing a tool defined in the profile's global tools list or a built-in/auto-mounted tool

#### Scenario: Start node exposes welcome fields

- **WHEN** the user selects the `start` node
- **THEN** the inspector shows editable `welcome_message` and `welcome_instructions`, persisted to the top-level config fields

#### Scenario: Deselect shows global settings

- **WHEN** no node is selected
- **THEN** the right panel shows the global settings (QA, Hours, Identity, Advanced) and the `global_prompt` editor

### Requirement: Dual editor modes with explicit strategy-change confirmation

The editor SHALL support both `prompt` and `graph` modes and SHALL allow switching between them. It SHALL provide a "Convert to graph" action that turns a single-`instructions` profile into a single-node graph following the equivalence defined by the graph schema. Because `editor_mode` is the sole runtime strategy-source switch (not a view preference), saving after a mode switch SHALL require an explicit confirmation stating that the save changes which strategy production executes. When switching back to `prompt` mode, the UI SHALL state that the prompt shown is the latest flattened representation of the graph and that further graph edits will not appear in prompt mode — it SHALL NOT present the revert as recovering the pre-conversion original.

#### Scenario: Convert to graph from prompt mode

- **WHEN** the user clicks "Convert to graph" on a prompt-mode profile
- **THEN** a single-node graph is created from the existing `instructions` and tools, and `editor_mode` becomes `graph`

#### Scenario: Mode-switch save requires confirmation

- **WHEN** the user switches editor mode and saves
- **THEN** a confirmation is shown stating the save changes the live runtime strategy source, and the save proceeds only on confirm

#### Scenario: Switch back to prompt mode

- **WHEN** the user switches a graph-mode profile back to `prompt` mode
- **THEN** the prompt-first editor is shown using the current (auto-regenerated) `instructions`, the graph is retained but not used, and the lossy nature of the revert is indicated

#### Scenario: Active source indication

- **WHEN** a profile is in `graph` mode
- **THEN** the UI indicates that the graph is the active driver of the conversation strategy

#### Scenario: Interim Try/deploy degradation banner

- **WHEN** a graph-mode profile is tried or deployed before `graph-runtime-executor` lands
- **THEN** the editor shows a persistent banner stating execution currently runs the auto-regenerated `instructions` fallback, rather than silently failing or silently degrading

### Requirement: Graph structure validation feedback

Before saving, the editor SHALL validate graph structure via `validateGraph(graph, availableTools)` and surface blocking errors and non-blocking warnings. Errors SHALL include: missing `start` node, more than one `start` node, duplicate node ids, edge endpoints referencing nonexistent nodes, nodes unreachable from `start` (a disconnected cycle must not pass a mere isolated-node check), edges targeting `start`, edges originating from `end`, and invalid `trigger` values. Warnings SHALL include: multiple unconditional out-edges on one source (under array-order priority, later ones are unreachable), and references to tool names outside the legal set. The legal tool set SHALL be the union of the profile's `config.tools` names, the built-in `availableTools` list, and the auto-mounted tool names (`lookup_qa`, `transfer_to_human`) — checking `config.tools` alone would false-positive on the handoff flow itself, since auto-mounted tools are deliberately stripped from `config.tools`. When `availableTools` fails to load, the tool-reference check SHALL be skipped rather than emitting false warnings. This frontend validation is UX feedback only; the authoritative runtime-gate validator is backend-owned by `graph-runtime-executor`.

#### Scenario: Blocking error prevents confusion

- **WHEN** the graph has no `start` node, more than one `start` node, or a node unreachable from `start`
- **THEN** the editor surfaces a blocking error identifying the problem

#### Scenario: Ambiguous branching warning

- **WHEN** a node has multiple outgoing unconditional edges
- **THEN** the editor surfaces a non-blocking warning that later edges are unreachable under array-order priority

#### Scenario: Auto-mounted tool is not a dangling reference

- **WHEN** a node references `transfer_to_human` or `lookup_qa`
- **THEN** no dangling-reference warning is raised, even though these names are absent from `config.tools`

#### Scenario: Dangling tool reference warning

- **WHEN** a node references a tool name outside the legal set (e.g. a deleted HTTP tool)
- **THEN** the editor surfaces a non-blocking warning listing the dangling reference and does not auto-remove the reference

### Requirement: Backward-compatible flow visualization

For profiles without a `graph` block, the editor SHALL continue to render the existing read-only flow visualization derived from the current config (instructions / qa / hours / handoff / tools), so list previews and prompt-mode profiles remain functional. The rewritten `buildFlowFromConfig` SHALL produce identical projections for legacy configs (regression-tested), since this is the only existing behavior this change touches.

#### Scenario: Legacy profile still renders a flow preview

- **WHEN** a profile has no `graph` block
- **THEN** the editor derives and renders the existing read-only hub-and-spoke flow projection from the config, unchanged from pre-change behavior
