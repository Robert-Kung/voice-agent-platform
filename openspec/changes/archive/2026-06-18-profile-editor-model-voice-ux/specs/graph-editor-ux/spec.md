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

- **WHEN** a graph-mode profile is tried or deployed — necessarily declaring `models.mode: pipeline`, because the graph×realtime combination cannot be saved (the backend returns 422; the in-editor realtime-tab case is governed by "Graph and realtime exclusivity feedback" in `profile-editor-stack-ux`, NOT by this scenario)
- **THEN** the editor indicates the graph executes natively in pipeline (graph-runtime-executor), and notes that a deployment-layer `AGENT_MODE` override can force realtime at deploy time — in which case the graph branches will not drive the conversation and execution degrades to the auto-regenerated flattened `instructions` — leading with that consequence before the mechanism. The editor SHALL NOT unconditionally claim a fallback or reference graph execution as "not yet landed", and SHALL NOT assert the actual runtime path as certain (it knows only the declared mode and that an env override can change it).
