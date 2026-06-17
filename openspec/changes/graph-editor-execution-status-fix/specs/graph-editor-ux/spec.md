## MODIFIED Requirements

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

#### Scenario: Deployment-aware execution status

- **WHEN** a graph-mode profile is tried or deployed
- **THEN** the editor indicates the execution path **implied by the profile-declared mode** (`models.mode`): pipeline implies the graph executes natively (graph-runtime-executor), realtime implies degradation to the auto-regenerated flattened `instructions` — leading with the user-facing consequence (in realtime the graph branches will not drive the conversation) before the mechanism, and noting a deployment-layer `AGENT_MODE` override can change the actual runtime path. The editor SHALL NOT unconditionally claim a fallback or reference graph execution as "not yet landed", and SHALL NOT assert the actual runtime path as certain (it only knows the profile-declared mode).

### Requirement: Graph structure validation feedback

Before saving, the editor SHALL validate graph structure via `validateGraph(graph, availableTools)` and surface blocking errors and non-blocking warnings. Errors SHALL include: missing `start` node, more than one `start` node, duplicate node ids, edge endpoints referencing nonexistent nodes, nodes unreachable from `start` (a disconnected cycle must not pass a mere isolated-node check), edges targeting `start`, edges originating from `end`, and invalid `trigger` values. Warnings SHALL include: multiple unconditional out-edges on one source (under array-order priority, later ones are unreachable), references to tool names outside the legal set, a `tool_result` edge sourced from a node with no domain tool (the transition can never fire), and a `tool_result` edge carrying a non-empty `condition` (v1 treats all `tool_result` transitions as unconditional, so the condition is ignored at runtime). The legal tool set SHALL be the union of the profile's `config.tools` names, the built-in `availableTools` list, and the auto-mounted tool names (`lookup_qa`, `transfer_to_human`) — checking `config.tools` alone would false-positive on the handoff flow itself, since auto-mounted tools are deliberately stripped from `config.tools`. When `availableTools` fails to load, the tool-reference check SHALL be skipped rather than emitting false warnings. This frontend validation is UX feedback only; the authoritative runtime-gate validator is backend-owned by `graph-runtime-validation`, and the warning rule set SHALL stay in parity with it.

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

#### Scenario: tool_result edge with a condition warns (backend parity)

- **WHEN** an edge has `trigger: tool_result` and a non-empty `condition`
- **THEN** the editor surfaces a non-blocking warning that v1 treats `tool_result` transitions as unconditional and the condition will be ignored at runtime, matching the backend validator's `tool_result_condition` warning

#### Scenario: Missing trigger with a condition does not warn

- **WHEN** an edge has no `trigger` field (coerced to `user_turn`) and a non-empty `condition`
- **THEN** no `tool_result_condition` warning is raised, matching the backend's `edge_trigger` coercion
