## ADDED Requirements

### Requirement: Editable graph canvas

The profile editor SHALL provide an editable graph canvas (built on the existing React Flow `agent-flow-builder` component) in which the user can add nodes, delete nodes, and connect nodes with edges. The canvas SHALL replace the prompt-first center pane when the profile's `editor_mode` is `graph`. Node positions changed on the canvas SHALL persist to each node's `position` field.

#### Scenario: Add a node

- **WHEN** the user adds a node of a chosen type (`prompt`, `handoff`, or `end`) on the canvas
- **THEN** a new node with a unique `id` and default fields is created and rendered

#### Scenario: Connect two nodes

- **WHEN** the user drags from one node's source handle to another node's target handle
- **THEN** a new edge with `source`, `target`, and an empty `condition` is created

#### Scenario: Delete a node

- **WHEN** the user deletes a node
- **THEN** the node and all edges referencing it are removed

#### Scenario: Persisted layout

- **WHEN** the user moves a node and saves
- **THEN** the node's `position` is persisted and restored on next open

### Requirement: Edge condition editing

The editor SHALL let the user edit each edge's natural-language `condition` and optional `label`. The condition SHALL be presented as free-text describing when the conversation transitions along that edge.

#### Scenario: Edit edge condition

- **WHEN** the user selects an edge and enters a natural-language condition
- **THEN** the edge's `condition` field is updated and the edge's `label` (if set) is shown on the canvas

### Requirement: Node inspector side panel

When a node is selected, the right panel SHALL switch to a Node Inspector showing that node's `title`, `prompt`, `tools`, and `variable_keys` for editing. The tools editor within the inspector SHALL reuse the existing tools UI and reference the profile's global tool list rather than redefining tools.

#### Scenario: Edit node prompt

- **WHEN** the user selects a node and edits its prompt in the inspector
- **THEN** the node's `prompt` field is updated

#### Scenario: Attach a tool to a node

- **WHEN** the user attaches a tool to the selected node
- **THEN** the tool's name is added to the node's `tools` array, referencing a tool defined in the profile's global tools list

#### Scenario: Deselect shows global settings

- **WHEN** no node is selected
- **THEN** the right panel shows the global settings (QA, Hours, Identity, Advanced) and the `global_prompt` editor

### Requirement: Dual editor modes and progressive migration

The editor SHALL support both `prompt` and `graph` modes and SHALL allow switching between them. It SHALL provide a "Convert to graph" action that turns a single-`instructions` profile into a single-node graph without data loss, following the equivalence defined by the graph schema. Switching back to `prompt` mode SHALL restore the prompt-first editor using the preserved `instructions`.

#### Scenario: Convert to graph from prompt mode

- **WHEN** the user clicks "Convert to graph" on a prompt-mode profile
- **THEN** a single-node graph is created from the existing `instructions` and tools, `editor_mode` becomes `graph`, and the original `instructions` is preserved

#### Scenario: Switch back to prompt mode

- **WHEN** the user switches a graph-mode profile back to `prompt` mode
- **THEN** the prompt-first editor is shown using the preserved `instructions` and the graph is retained but not used

#### Scenario: Active source indication

- **WHEN** a profile is in `graph` mode
- **THEN** the UI indicates that the graph is the active driver of the conversation strategy

### Requirement: Graph structure validation feedback

Before saving, the editor SHALL validate graph structure and surface blocking errors and non-blocking warnings. Errors SHALL include: missing `start` node, more than one `start` node, and duplicate node ids. Warnings SHALL include: isolated nodes (no incoming or outgoing edge), an empty edge `condition` where the source node has multiple outgoing edges (ambiguous branching), and references to tool names not present in the profile's global tools list.

#### Scenario: Blocking error prevents confusion

- **WHEN** the graph has no `start` node or more than one `start` node
- **THEN** the editor surfaces a blocking error identifying the problem

#### Scenario: Ambiguous branching warning

- **WHEN** a node has multiple outgoing edges and one of them has an empty `condition`
- **THEN** the editor surfaces a non-blocking warning about ambiguous branching

#### Scenario: Dangling tool reference warning

- **WHEN** a node references a tool name that is not in the profile's global tools list
- **THEN** the editor surfaces a non-blocking warning listing the dangling reference and does not auto-remove the reference

### Requirement: Backward-compatible flow visualization

For profiles without a `graph` block, the editor SHALL continue to render the existing read-only flow visualization derived from the current config (instructions / qa / hours / handoff / tools), so list previews and prompt-mode profiles remain functional.

#### Scenario: Legacy profile still renders a flow preview

- **WHEN** a profile has no `graph` block
- **THEN** the editor derives and renders the existing read-only hub-and-spoke flow projection from the config
