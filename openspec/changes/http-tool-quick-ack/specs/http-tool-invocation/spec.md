# Spec Delta: http-tool-invocation (http-tool-quick-ack)

## ADDED Requirements

### Requirement: HTTP tool response mode configuration
HTTP tool config SHALL accept an optional `response_mode` field with value `wait` or `quick_ack`. When absent, the mode SHALL default to `wait`, preserving existing behavior. An invalid `response_mode` value SHALL raise `ValueError` at tool build time, causing the tool to be skipped and logged by `build_tools_for_agent` without crashing agent startup.

#### Scenario: Default mode is wait
- **WHEN** an HTTP tool config omits `response_mode`
- **THEN** the tool waits for the HTTP response before returning, identical to existing behavior

#### Scenario: Invalid mode rejected at build time
- **WHEN** an HTTP tool config sets `response_mode: fire`
- **THEN** `make_http_tool` raises `ValueError` mentioning `response_mode`

#### Scenario: Valid modes accepted
- **WHEN** an HTTP tool config sets `response_mode` to `wait` or `quick_ack`
- **THEN** the tool builds successfully

### Requirement: Quick-ack mode returns immediately and dispatches in background
When `response_mode` is `quick_ack`, the tool handler SHALL dispatch the HTTP request as a background asyncio task and immediately return an acknowledgement payload `{"success": true, "accepted": true, "detail": <submitted message>}` without waiting for the HTTP response. The background task SHALL apply the configured `timeout_seconds`, SHALL be retained (not garbage-collected) until completion, and SHALL log the final outcome: info on success, warning on HTTP error / timeout / connection failure. The background outcome SHALL NOT be surfaced to the conversation.

#### Scenario: Immediate acknowledgement
- **WHEN** a quick_ack tool is invoked and the endpoint takes longer than `timeout_seconds` to respond
- **THEN** the handler returns `{"success": true, "accepted": true, ...}` immediately, before the endpoint responds

#### Scenario: Background success is logged
- **WHEN** the background request completes with a 2xx response
- **THEN** an info log records the tool name and success outcome

#### Scenario: Background failure is logged as warning
- **WHEN** the background request fails (HTTP >= 400, timeout, or connection error)
- **THEN** a warning log records the tool name and failure detail, and no exception propagates

### Requirement: Wait mode timeout returns pending semantics
When `response_mode` is `wait` and the request exceeds `timeout_seconds`, the handler SHALL return `{"success": false, "pending": true, "error": "timeout", "detail": ...}` where `detail` states that the request was submitted, the backend may still be processing, and the request must not be re-submitted. Non-timeout failures (HTTP >= 400, connection errors) SHALL keep the existing `{"success": false, "error": ...}` shape without `pending`.

#### Scenario: Timeout returns pending
- **WHEN** a wait-mode tool call exceeds `timeout_seconds`
- **THEN** the result has `success: false`, `pending: true`, and a detail instructing not to re-submit

#### Scenario: HTTP error unchanged
- **WHEN** a wait-mode tool call receives an HTTP 500 response
- **THEN** the result has `success: false` with status and error text, and no `pending` field

#### Scenario: Connection error unchanged
- **WHEN** a wait-mode tool call fails with a connection error
- **THEN** the result has `success: false` with a connection error message, and no `pending` field

### Requirement: Admin UI exposes response mode
The Profile Editor HTTP tool card SHALL provide a control to select `response_mode` between wait and quick_ack, persisted through the profile form's HTTP tool config. An unset value SHALL be treated as `wait`.

#### Scenario: Selecting quick_ack persists
- **WHEN** an admin sets a tool's response mode to quick_ack and saves the profile
- **THEN** the saved tool config contains `response_mode: quick_ack`

#### Scenario: Existing tools unchanged
- **WHEN** an existing profile with HTTP tools lacking `response_mode` is loaded
- **THEN** the UI shows wait mode and saving does not alter runtime behavior
