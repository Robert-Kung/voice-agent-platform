# graph-execution Specification

## Purpose
TBD - created by archiving change graph-runtime-executor. Update Purpose after archive.
## Requirements
### Requirement: Strategy-source gate selects graph execution

The runtime SHALL execute the graph as the conversation strategy if and only if ALL of the following hold: `editor_mode` is `graph`, the `graph` block passes the backend structural validator (see `graph-runtime-validation`), and the effective agent mode is `pipeline`. When any condition fails, the runtime SHALL fall back to the profile's `instructions` string, emit a warning log identifying the reason, and proceed with the call. The runtime SHALL NOT raise or drop the call when the graph is unusable — a broken conversation strategy is inaudible-degraded, never a disconnect. The `graph` + `realtime` combination is blocked at save time (see `graph-runtime-validation`); the realtime branch of this gate is the misconfiguration net for cases that bypass the save block (e.g. a deployment-level `AGENT_MODE=realtime` env override of a graph profile).

#### Scenario: Graph mode, valid graph, pipeline mode

- **WHEN** a profile has `editor_mode: graph`, a graph that passes the backend validator, and runs under pipeline mode
- **THEN** the runtime assembles and runs the graph as the conversation strategy

#### Scenario: Graph mode but validator fails

- **WHEN** a profile has `editor_mode: graph` but its graph fails the backend validator
- **THEN** the runtime falls back to the `instructions` string, logs a warning naming the validation failure, and the call proceeds

#### Scenario: Prompt mode profile is unaffected

- **WHEN** a profile has `editor_mode: prompt` (or no `editor_mode`)
- **THEN** the runtime uses the existing single-`instructions` path with no graph assembly

#### Scenario: Graph mode under realtime falls back

- **WHEN** a graph-mode profile runs under realtime mode
- **THEN** the runtime falls back to the regenerated `instructions` (graph execution v1 is pipeline-only) and logs the reason

### Requirement: Node-to-Agent assembly via SDK-native handoff

The runtime SHALL realize each graph node as a distinct LiveKit Agents `Agent` instance rather than a self-built state machine. Each node's Agent SHALL be constructed with `instructions` composed of the global preamble (`global_prompt` plus globally-injected capabilities) followed by the node's focused `prompt`, and with `tools` comprising the node's declared tools (resolved through the profile's existing three-tier tool-mounting rules) plus the generated transition tools for that node's outgoing edges. Edge transitions SHALL be implemented as SDK handoffs in which a tool returns the target node's Agent instance, triggering its `on_enter`. The `start` node's Agent SHALL be the session's initial agent.

#### Scenario: Each node becomes an Agent with composed instructions

- **WHEN** the runtime assembles a valid graph
- **THEN** every node yields one Agent whose instructions are the global preamble followed by that node's `prompt`, and whose tools include the node's declared tools

#### Scenario: Start node is the entry Agent

- **WHEN** the graph is assembled
- **THEN** the session starts on the Agent built from the unique `start` node

#### Scenario: Transition performs an SDK handoff

- **WHEN** a transition to a target node is triggered
- **THEN** the runtime hands off to the target node's Agent instance via the SDK's agent-handoff mechanism, invoking the target's `on_enter`

### Requirement: User-turn edge transitions are LLM-evaluated

For each outgoing edge with `trigger: user_turn`, the runtime SHALL generate a transition tool whose description conveys the edge's natural-language `condition`, so the LLM calls it after a user turn when that condition holds. An empty `condition` SHALL be represented as an unconditional transition reflected in the node's instructions. When multiple outgoing edges from one node could match, the runtime SHALL respect the `edges` array order as priority (first match wins) by generating and listing transitions in that order.

#### Scenario: Conditional user-turn transition

- **WHEN** a node has a `user_turn` edge with a non-empty `condition`
- **THEN** a transition tool is generated whose description reflects that condition, and calling it hands off to the target

#### Scenario: Array-order priority among matching edges

- **WHEN** a node has multiple outgoing edges that could apply
- **THEN** the runtime presents and prioritizes them in `edges` array order so the first match wins

### Requirement: Tool-result edge transitions fire unconditionally without a user turn

For a node with outgoing `trigger: tool_result` edges, the runtime SHALL transition after the node's domain tool returns, without waiting for a user turn, by having the domain tool return the target node's Agent (the SDK handoff path). v1 SHALL treat all `tool_result` transitions as unconditional: after the domain tool completes, the runtime hands off to the target of the highest-priority (`edges` array order) outgoing `tool_result` edge. v1 SHALL NOT honor a non-empty `condition` on a `tool_result` edge — the schema has no tool↔edge binding and such a condition would require a non-deterministic LLM evaluation at the latency-sensitive post-tool point; instead the backend validator SHALL warn on a non-empty `tool_result` condition and the runtime SHALL treat it as unconditional and log it.

#### Scenario: Immediate handoff after tool returns

- **WHEN** a node's domain tool returns and the node has an outgoing `tool_result` edge
- **THEN** the runtime immediately hands off to that edge's target without a user turn

#### Scenario: Non-empty tool_result condition is treated as unconditional

- **WHEN** a `tool_result` edge declares a non-empty `condition`
- **THEN** v1 ignores the condition (validator warns at save time), transitions unconditionally after the domain tool returns, and logs that the condition was not honored

### Requirement: Global capabilities are injected at the global level

The runtime SHALL inject QA-inline content, services-hours content, and `global_prompt` into the global preamble composed with every node's instructions, not into individual nodes. When `qa_mode` is `tool`, `lookup_qa` SHALL remain mounted on every node's Agent. `transfer_to_human` SHALL NOT be unconditionally mounted on every node; it SHALL be invoked when a `handoff` node activates, using that node's `prompt` as the per-handoff greeting/instructions.

#### Scenario: QA and hours injected globally

- **WHEN** a graph-mode profile has QA-inline data or services hours
- **THEN** that content is composed into the global preamble shared by all node Agents, not duplicated per node

#### Scenario: Handoff node invokes transfer_to_human

- **WHEN** a `handoff` node activates during graph execution
- **THEN** the runtime invokes `transfer_to_human`, using the node's `prompt` as the handoff greeting

#### Scenario: transfer_to_human not globally mounted

- **WHEN** a graph has no active handoff node in the current turn
- **THEN** `transfer_to_human` is not offered as a globally-mounted tool on arbitrary nodes

### Requirement: Per-node model declaration interface

When a node declares a model specification, the runtime SHALL resolve that node's model components through the same `agents/runtime/providers.py` `build_*` functions used for session-level resolution, and SHALL record cost using the session row's extensible model-name structure. v1 MAY provide only the interface (resolution call site with fallback to the session-level model) without guaranteeing full per-node model switching.

#### Scenario: Node without a model spec uses the session model

- **WHEN** a node declares no model specification
- **THEN** the node's Agent uses the session-level resolved model components

#### Scenario: Node model spec routes through the shared resolver

- **WHEN** a node declares a model specification
- **THEN** the runtime resolves it via the same `build_*` provider functions rather than a separate code path

