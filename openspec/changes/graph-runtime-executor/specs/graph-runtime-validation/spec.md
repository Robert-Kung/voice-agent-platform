## ADDED Requirements

### Requirement: Backend structural validator is the runtime gate's single source of truth

The system SHALL provide a backend (Python) graph validator that is the authoritative structural check for both the runtime execution gate and API save-time hard validation. The frontend `validateGraph` SHALL remain UX feedback only and SHALL NOT be the gate, because direct API writes can bypass it. The backend validator SHALL return a structured result distinguishing blocking errors from non-blocking warnings, and SHALL expose a boolean validity equal to "no errors".

#### Scenario: Validator result distinguishes errors from warnings

- **WHEN** the backend validator runs on a graph
- **THEN** it returns separate error and warning collections and a validity flag that is true exactly when there are no errors

#### Scenario: Frontend validator is advisory only

- **WHEN** a graph is written directly via the API, bypassing the frontend
- **THEN** the backend validator still gates execution and save, so the frontend `validateGraph` being skipped does not let an invalid graph through

### Requirement: Validator rule parity with the frontend rule set

The backend validator SHALL enforce the same structural rule set as the frontend `validateGraph`. Blocking errors SHALL include: exactly one `start` node (zero or multiple is an error), unique node ids, unique edge ids, every node `type` is one of the legal types, every edge `source` and `target` references an existing node, no edge targets the `start` node, no edge originates from an `end` node, every edge `trigger` (when present) is a legal value, and every node is reachable from `start` (breadth-first). Warnings SHALL include: self-loop edges, multiple unconditional out-edges sharing one `(source, trigger)`, references to tools outside the legal tool set, and a `handoff` node present while handoff is disabled.

#### Scenario: Missing or duplicate start node is an error

- **WHEN** a graph has zero or more than one `start` node
- **THEN** the validator reports a blocking error and validity is false

#### Scenario: Edge into start or out of end is an error

- **WHEN** an edge targets the `start` node or originates from an `end` node
- **THEN** the validator reports a blocking error

#### Scenario: Unreachable node is an error

- **WHEN** a node cannot be reached from the `start` node by following edges
- **THEN** the validator reports a blocking error naming the node

#### Scenario: Illegal trigger is an error

- **WHEN** an edge has a `trigger` value outside the legal set
- **THEN** the validator reports a blocking error

#### Scenario: Dangling tool reference is a warning

- **WHEN** a node references a tool not in the legal set (profile tools, builtins, auto-mounted tools)
- **THEN** the validator reports a non-blocking warning and validity is unaffected

### Requirement: Graph and realtime mode are mutually exclusive

The backend validator SHALL treat the combination of `editor_mode: graph` and an explicit realtime mode (`models.mode: realtime`) as a blocking error, because graph node execution requires mid-session instruction swaps that the Gemini Live realtime backend either rejects (1007 after the first model turn) or silently ignores. The agent mode is not editable in the profile editor (it is determined by deployment env / the profile's `models.mode`), so the frontend SHALL surface a graph-mode hint that execution requires pipeline deployment (UX feedback only; the backend block is the enforced gate). Graph execution under pipeline mode is a full production path and SHALL NOT be flagged.

#### Scenario: Graph mode with realtime is a blocking error

- **WHEN** a profile has `editor_mode: graph` and `models.mode: realtime`
- **THEN** the validator reports a blocking error and the save is rejected

#### Scenario: Graph mode with pipeline is allowed

- **WHEN** a profile has `editor_mode: graph` and `models.mode: pipeline` (or no mode, resolving to the deployment default for that profile)
- **THEN** the validator does not flag the mode pairing

### Requirement: Tool-result edge with a non-empty condition is a warning

The backend validator SHALL emit a non-blocking warning when an edge has `trigger: tool_result` and a non-empty `condition`, because v1 does not honor conditional tool-result transitions (no tool↔edge binding exists in the schema and a post-tool LLM evaluation is non-deterministic at a latency-sensitive point). The save SHALL still succeed; the runtime treats the transition as unconditional.

#### Scenario: Non-empty tool_result condition warns but does not block

- **WHEN** an edge has `trigger: tool_result` and a non-empty `condition`
- **THEN** the validator reports a non-blocking warning and validity is unaffected

### Requirement: API save enforces hard validation in graph mode

When a profile create or update carries `editor_mode: graph`, the API SHALL run the backend validator before persisting and SHALL reject the write with a client error (HTTP 422) when the graph has blocking errors. This closes the gap where direct API writes bypass the frontend save gate. Saves for `prompt`-mode profiles (or with no graph) SHALL pass through unchanged.

#### Scenario: Invalid graph-mode save is rejected

- **WHEN** a profile is saved with `editor_mode: graph` and a graph that has blocking errors
- **THEN** the API responds with HTTP 422 and does not persist the change

#### Scenario: Valid graph-mode save is persisted

- **WHEN** a profile is saved with `editor_mode: graph` and a graph with no blocking errors
- **THEN** the API persists the config

#### Scenario: Prompt-mode save bypasses graph validation

- **WHEN** a profile is saved with `editor_mode: prompt` or with no graph block
- **THEN** the API persists without running graph structural validation
