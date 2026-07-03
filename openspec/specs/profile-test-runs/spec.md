# profile-test-runs Specification

## Purpose
Deterministic profile flow test: verify saved prompt/graph wiring without LLM, LiveKit room, or external side effects. Created by archiving change profile-test-runs.
## Requirements

### Requirement: Profile flow test run creation

The system SHALL allow an authenticated admin user to create a flow test run for a saved profile by providing a sample user message and optional execution settings. The flow test SHALL load the saved profile, snapshot the profile id/config hash at run creation, apply the same profile normalization and strategy-source selection rules used by runtime, and execute without calling an LLM, requiring a LiveKit room, microphone, STT, or TTS. For graph-mode profiles, the test SHALL validate and deterministically execute one smoke/debug graph path when graph execution is valid for pipeline mode; otherwise it SHALL record the fallback reason and test the flattened prompt wiring path. A flow test result SHALL be labeled as one authoring/debug run and SHALL NOT be presented as proof that LLM reasoning, voice Try, STT/TTS, SIP, or external live integrations will succeed.

#### Scenario: Create a flow test run for graph profile

- **WHEN** an admin starts a flow test run for a saved graph-mode profile with valid graph execution settings
- **THEN** the system creates a run, evaluates the saved graph wiring through the deterministic smoke strategy, and records the visited node path

#### Scenario: Profile snapshot is recorded

- **WHEN** a flow test run is created for a profile
- **THEN** the run summary records the profile id, profile config hash, and snapshot timestamp used for that run

#### Scenario: Create a flow test run for prompt profile

- **WHEN** an admin starts a flow test run for a prompt-mode profile
- **THEN** the system creates a run using the prompt wiring strategy and records that no graph node path is active

#### Scenario: Graph fallback is visible

- **WHEN** a flow test run targets a graph-mode profile whose graph cannot execute under the runtime gate
- **THEN** the run records a warning event with the fallback reason and continues through the flattened prompt strategy

### Requirement: Structured test run event log

The system SHALL persist or otherwise make queryable a structured event log for each profile test run. Events SHALL be ordered and SHALL include a timestamp, event type, severity, and JSON payload with `schema_version: 1`. The event model SHALL support user input, placeholder output, node entry, edge selection, tool call, tool result, handoff, warning, error, tool timeout, graph fallback, and run completion events. Event payloads SHALL be sanitized before storage and before API responses so secrets, authorization headers, query-string credentials, and sensitive environment values are not exposed to the frontend.

#### Scenario: Events are ordered and typed

- **WHEN** a test run produces multiple runtime events
- **THEN** the API returns those events in execution order with stable event types and timestamps

#### Scenario: Tool event payloads are sanitized

- **WHEN** a tool call event includes request metadata
- **THEN** secrets and authorization values are redacted before the event is stored or returned

#### Scenario: Event schema version is included

- **WHEN** the API returns test run events
- **THEN** every event payload includes `schema_version: 1` so old runs remain parseable after future payload changes

#### Scenario: Run completion has final status

- **WHEN** a test run finishes, fails, or is cancelled
- **THEN** the event log includes a run completion event and the run summary exposes the final status

### Requirement: Tool execution mode for tests

The system SHALL support an explicit tool execution mode for profile flow tests. The default mode SHALL be `dry_run`, in which external side-effect tools validate inputs and emit planned-call events without performing the external action. A `live` mode SHALL record explicit live-mode intent and a structured not-enabled result until flow-test live execution is implemented; real external side effects remain covered by voice Try/session logs in this iteration. Tool execution SHALL go through a central test-run dispatcher that records mode, timeout, result, and error state consistently for every tool. Every tool call event SHALL identify whether it was dry-run or live.

#### Scenario: Dry-run is the default

- **WHEN** an admin starts a flow test run without choosing a tool execution mode
- **THEN** external side-effect tools are not executed live and the event log marks them as dry-run

#### Scenario: Live mode records explicit intent

- **WHEN** an admin starts a flow test run with live tool execution enabled
- **THEN** the event log marks each tool call as live, records that flow-test live execution is not enabled, and does not perform external side effects

#### Scenario: Tool schema problems are visible

- **WHEN** a tool cannot be invoked because required arguments are missing or invalid
- **THEN** the run records a tool error event with a user-readable reason and does not silently pass

#### Scenario: Tool timeout is bounded

- **WHEN** a live or dry-run tool exceeds the configured test timeout
- **THEN** the run records a timeout event with the tool name, mode, and elapsed duration, and the test run continues or fails according to the configured status transition

### Requirement: Test run status machine

The system SHALL expose a finite status machine for flow test runs. Valid statuses SHALL be `created`, `running`, `completed`, `failed`, and `cancelled`. A run SHALL transition from `created` to `running` when execution starts, and then to exactly one terminal status. A run with tool validation warnings MAY complete successfully when the deterministic flow path produced a usable result; a run with unhandled runner, profile loading, auth, or persistence errors SHALL finish as `failed` while preserving events recorded before the failure whenever possible.

#### Scenario: Successful run completes

- **WHEN** a flow test run finishes without unhandled errors
- **THEN** the run status is `completed` and the event log includes a run completion event

#### Scenario: Runner failure preserves partial events

- **WHEN** a flow test run fails after some events have been recorded
- **THEN** the run status is `failed` and the API can still retrieve the partial event log

### Requirement: Test run API access

The system SHALL provide authenticated admin API endpoints to create a profile flow test run, retrieve a test run with its events, and list recent test runs for a profile. The endpoints SHALL use the profile-scoped resource shape `POST /api/profiles/{profile_id}/test-runs`, `GET /api/profiles/{profile_id}/test-runs`, and `GET /api/profiles/{profile_id}/test-runs/{run_id}`. List responses SHALL be scoped to a profile and SHALL support `limit` and `offset` parameters consistent with existing session listing APIs, including a total count or equivalent `has_more` signal.

#### Scenario: Create run API returns run summary

- **WHEN** the frontend creates a flow test run through the admin API
- **THEN** the response includes the run id, profile id, status, final summary, and enough event data to render the immediate result

#### Scenario: API error includes run id when available

- **WHEN** a flow test API request fails after a run record has been created
- **THEN** the error response includes the run id and a user-readable reason so the editor can link to partial events

#### Scenario: List recent runs for profile

- **WHEN** the frontend requests recent test runs for a profile
- **THEN** the API returns only runs for that profile within the configured limit or page

#### Scenario: Unauthenticated access is rejected

- **WHEN** a request without valid admin authentication accesses test run APIs
- **THEN** the API rejects the request using the same admin auth policy as other profile management APIs

### Requirement: Profile Editor flow test panel

The Profile Editor SHALL provide a flow test entry point that lets an admin enter a sample user message, choose the tool execution mode, start a run, and inspect the resulting event log without leaving the profile. The UI SHALL show run status, placeholder output when available, graph node path when available, edge decisions, tool-call states, warnings, errors, and handoff outcome. In graph mode, the UI SHALL visually distinguish the visited path from unvisited graph nodes when run data is available. The UI SHALL explicitly distinguish flow tests from LLM-backed text tests and voice Try, and SHALL explain that dry-run tool results do not validate external service availability.

#### Scenario: Start flow test from editor

- **WHEN** an admin enters a message in the Profile Editor test panel and starts a run
- **THEN** the editor calls the flow test API and shows progress and results for that run

#### Scenario: Inspect graph path and tool states

- **WHEN** a graph-mode flow test run includes node transitions and tool calls
- **THEN** the editor displays the visited graph path and each tool call state as pending, success, dry-run, timeout, or error as applicable

#### Scenario: Tool mode is visible before and after run

- **WHEN** an admin starts or inspects a flow test run
- **THEN** the editor shows whether tools are in `dry_run` or `live` mode near the run control and on each tool event row

#### Scenario: Fallback warning is prominent

- **WHEN** a graph-mode test falls back to flattened prompt execution
- **THEN** the editor shows a warning banner and a timeline warning event with the fallback reason

#### Scenario: Timeline rows are inspectable and accessible

- **WHEN** a run event includes structured payload data
- **THEN** the editor renders a compact row with status, timestamp, type, and an accessible expand control for sanitized details

#### Scenario: Prompt profile still has useful output

- **WHEN** a prompt-mode flow test run completes
- **THEN** the editor displays the user input, placeholder output, warnings/errors, and final status without requiring graph-specific data

### Requirement: Test coverage for profile test runs

The implementation SHALL include backend tests for flow test run creation, graph fallback logging, event ordering, dry-run tool behavior, and auth enforcement. It SHALL include frontend tests for starting a run, rendering event timelines, displaying graph path/tool states, and handling API errors. It SHALL include at least one fixture-based graph test that exercises a `user_turn` transition and one that exercises a `tool_result` transition in flow-test mode.

#### Scenario: Backend test covers graph route

- **WHEN** the backend test suite runs
- **THEN** it verifies that a graph flow test records node transition and edge selection events

#### Scenario: Backend test covers dry-run tools

- **WHEN** the backend test suite runs a flow test with a side-effect tool in default mode
- **THEN** it verifies that the external action is not performed and a dry-run tool event is recorded

#### Scenario: Frontend test covers result rendering

- **WHEN** the frontend test suite renders a completed graph test run
- **THEN** it verifies that the editor shows the run status, visited path, and tool-call state