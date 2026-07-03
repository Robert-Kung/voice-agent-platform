## Context

Profile Editor v2 can now author prompt and graph profiles, and graph execution is available in pipeline mode. The remaining testing workflow is still voice-first: a user starts a LiveKit Try room, speaks through STT/TTS, and inspects raw logs when something goes wrong. That path is necessary for final e2e validation, but it is too slow and too opaque for routine profile authoring.

The next layer should introduce a text-first test run path and a structured event log. The goal is not to replace voice Try, but to make graph routing, tool behavior, and handoff outcomes visible before involving microphone, room lifecycle, STT, TTS, or external network conditions.

## Goals / Non-Goals

**Goals:**

- Provide a flow test entry point for a saved profile.
- Record each test as a structured run with ordered events.
- Surface node path, edge decisions, tool calls, tool outcomes, warnings, and final status in the Profile Editor.
- Share profile loading, normalization, graph validation, and graph/prompt strategy selection with the production runtime where practical.
- Default to side-effect-safe tool behavior for flow tests while exposing explicit live-mode intent without external execution in this iteration.

**Non-Goals:**

- Replace LiveKit voice Try or SIP/voice e2e validation.
- Implement a full chat simulator with long-lived memory across many turns in the first iteration.
- Add AI-generated graph drafts.
- Add per-node model switching.
- Build a general observability product for production sessions; this change is scoped to profile test runs.

## Decisions

### Decision: Introduce profile-scoped test runs instead of overloading sessions

Test runs should be separate from live session rows because their lifecycle, inputs, and safety semantics differ from real calls. A flow test run can complete in seconds, may use dry-run tools, and should be easy to replay or delete without affecting customer session history.

Alternative considered: reuse the existing session/cost tables. This would reduce schema work, but it would mix authoring tests with real user calls and make future filtering/auditing harder.

### Decision: Store ordered event records with typed payloads

Each run should expose an ordered timeline rather than only a final transcript. Event types should cover `user_input`, `assistant_output`, `node_enter`, `edge_selected`, `tool_call`, `tool_result`, `handoff`, `warning`, `error`, and `run_completed`. Payloads should be JSON objects so backend tests and frontend UI can evolve without parsing log strings.

Every event payload should include `schema_version: 1`. The API should sanitize payloads before persistence and before response serialization, using an allowlist-first strategy for request/response metadata. Secret-like keys, authorization headers, credentials, and environment-derived values should be redacted in nested objects, headers, query parameters, and tool config snapshots.

Alternative considered: persist raw log lines. Raw logs are cheap, but they are not stable enough for UI state, assertions, or replay.

### Decision: Flow tests use deterministic runtime adapters, not an LLM or LiveKit room

The flow test path should avoid LLM calls, LiveKit room setup, microphone permissions, STT, and TTS. It should still reuse profile parsing, graph validation, flattened prompt generation, tool registry resolution, and graph transition semantics where practical. If the production LiveKit `Agent` abstraction is too tightly bound to a live `RunContext`, implement a small adapter layer that emits test-run events around deterministic graph decisions and tool calls.

Alternative considered: spin up a full LiveKit room or call the configured LLM for this panel. That would improve behavioral fidelity, but it belongs in the next LLM-backed text runner; this change establishes the flow/run-log infrastructure first.

### Decision: Tool execution mode is explicit and safe by default

Flow tests should default to `dry_run` tool mode. In dry-run mode, built-in and HTTP tools should validate inputs and emit planned request metadata without performing external side effects. In this iteration, `live` mode records explicit live-mode intent and a structured not-enabled result; real external validation remains in voice Try/session logs until flow-test live execution has a side-effect contract.

Dry-run behavior should be implemented through a central test-run tool dispatcher rather than ad hoc branches inside every tool. The dispatcher should know whether a tool is side-effecting, record a planned call in dry-run mode, and record live-mode intent without external execution for now. Text-mode handoff should record `handoff_attempted` / `handoff` events rather than trying to transfer a real voice session.

Alternative considered: always execute tools live. The recent LINE ticket verification showed live tools are valuable, but making that the default risks duplicate tickets and confusing side effects during routine authoring.

### Decision: Snapshot profile configuration at run creation

Test runs should record the profile id, a configuration hash, and the created-at timestamp of the profile configuration used for the run. This prevents a confusing class of bugs where an author edits a profile while reading an older result and cannot tell which config produced the events.

Alternative considered: always read the latest profile when retrieving a run. That is simpler, but it makes historical test results impossible to explain once tools, graph edges, or prompt text change.

### Decision: The first UI should be a compact editor test panel

The Profile Editor should expose a text input, run status, event timeline, and graph path/tool state summary. The panel should be useful in both prompt and graph modes, with graph-specific node/path highlighting only when a graph is active.

The compact panel should lead with input, tool mode, run button, current status, and placeholder output. Detailed timeline rows, payloads, graph path, and recent runs should live behind expandable sections. The UI must label flow tests as deterministic authoring/debug checks and keep voice Try visible as the final integration check for LLM behavior, audio, STT/TTS, and external live behavior.

Alternative considered: build a separate full testing page first. A separate page may be useful later, but putting the first version in the editor keeps the test loop close to the profile being edited.

## Risks / Trade-offs

- Flow-test behavior diverges from voice/text LLM runtime -> Share normalization, validation, graph flattening, and transition logic; clearly label LLM/voice-only risks that still require a later text runner or Try.
- Dry-run tools hide integration failures -> Provide explicit live-mode intent and event metadata that shows when a tool was skipped; keep real external validation in voice Try until flow-test live execution has a side-effect contract.
- Event payloads leak sensitive request data -> Store sanitized payloads by default; redact secrets, auth headers, and large bodies.
- Test run storage grows without bound -> Add retention limits or pagination from the first API version.
- UI becomes too heavy inside the editor -> Keep the first panel compact and focused on current/recent runs, with deeper replay deferred.
- Deterministic graph smoke paths can create false confidence -> Label the selected path as deterministic v1 behavior, add automatic route coverage as a follow-up, and keep LLM-backed text testing/voice Try as the behavioral validation path.