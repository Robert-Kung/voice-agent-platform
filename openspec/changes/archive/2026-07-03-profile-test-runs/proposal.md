## Why

Graph agent e2e is now viable, but the current testing workflow still depends on live voice sessions and raw logs to understand what happened. Profile authors need a faster, lower-friction way to test a graph with text input and inspect the resulting node path, edge decisions, tool calls, and handoff outcome.

## What Changes

- Add a structured test run model for profile tests, with ordered events for user input, node transitions, tool calls, tool results, warnings/errors, and final status.
- Add a flow test entry point that exercises saved prompt/graph/tool wiring through the same normalization and graph gate used by runtime, without calling an LLM or requiring microphone, LiveKit room setup, STT, or TTS.
- Add API surfaces to create a flow test run and read recent test runs/events for a profile.
- Add Profile Editor UI affordances to start a flow test and inspect the resulting run log, including deterministic graph path and tool-call states.
- Keep voice Try as a separate integration path for now; this change does not replace LiveKit voice e2e.

## Capabilities

### New Capabilities

- `profile-test-runs`: Defines profile flow test execution, structured test run/event logging, and editor-facing test result inspection.

### Modified Capabilities

- None.

## Impact

- Backend API: new admin test-run endpoints and response schemas.
- Backend runtime: reusable flow-test execution path that shares profile loading, graph validation, graph assembly, tool invocation policy, and fallback behavior where practical.
- Database: persisted or queryable test run/event records scoped to profile and session-independent test execution.
- Frontend: Profile Editor test panel/entry point and run-log display for flow tests.
- Tests: backend API/runtime tests, frontend component/unit tests, and fixture coverage for graph flow-test paths.