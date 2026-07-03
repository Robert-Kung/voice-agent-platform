# Profile Flow Test Guide

Profile Flow Test gives profile authors a fast feedback loop inside the Profile Editor. It runs a single saved sample message through the profile's prompt or graph wiring, stores a structured test run log, and renders the result beside the editor.

It does not call an LLM, start a LiveKit room, or replace voice Try. Use Flow Test for authoring/debugging saved prompt, graph, tool, handoff, fallback, and event-log wiring. Use voice Try for real LLM behavior, audio, STT/TTS, LiveKit handoff behavior, SIP/browser integration, and real external side effects.

Current v1 behavior is deterministic. The sample message is recorded and passed through event payloads, but it does not semantically choose a graph path. For graph profiles, the runner enters the start node, records declared tool calls, selects the first `tool_result` edge when present, otherwise selects the first `user_turn` edge, and records the resulting node path. It does not automatically enumerate every graph route yet.

## Where It Lives

Open `/admin/profiles/{profile_id}` and use the right-side `Flow Test` panel.

The panel is intentionally next to the flow/global settings area so graph authors can inspect the graph while running a message. Unsaved profile edits are not included; save before testing the latest draft.

## Tool Modes

`dry_run` is the default and safe mode.

- Records planned tool calls.
- Suppresses external side effects.
- Preserves tool name, method, endpoint, timeout metadata, and a consistent dry-run result shape.
- Redacts sensitive payload values before storage/API output.

`live` currently records live-mode intent and returns a structured not-enabled result for flow tests. Voice Try remains the path for real integration validation.

## Event Types

Every event payload includes `schema_version: 1`.

Common event types:

| Event | Meaning |
|---|---|
| `test_started` | Run metadata, profile config hash, input message, flow-vs-voice/LLM caveat |
| `prompt_rendered` | Prompt-mode path used the flattened/system instructions |
| `graph_validated` | Graph-mode path passed validator and can be simulated |
| `node_entered` | Flow runner visited a graph node |
| `edge_selected` | Flow runner selected a graph edge (`user_turn` or `tool_result`) |
| `tool_call` | Tool dispatcher planned or attempted a tool call |
| `tool_result` | Tool result shape used for graph transition logging |
| `handoff` | Graph path reached a handoff node |
| `fallback` | Graph execution was unavailable and degraded to prompt/flattened path |
| `assistant_output` | Placeholder output for this single-turn flow run; not an LLM response |
| `timeout` | Run-level or tool-level timeout contract event |
| `runner_error` | Runner failure preserved as an event before terminal status |

## Statuses

A run status is one of:

- `created`
- `running`
- `completed`
- `failed`
- `cancelled`

The current API executes synchronously, so successful UI runs normally return `completed` immediately.

## API

All endpoints are profile-scoped and require admin auth when `ADMIN_API_TOKEN` is configured.

```http
POST /api/profiles/{profile_id}/test-runs
Content-Type: application/json

{
  "message": "電梯壞了，請幫我報修",
  "tool_execution_mode": "dry_run"
}
```

```http
GET /api/profiles/{profile_id}/test-runs?limit=50&offset=0
GET /api/profiles/{profile_id}/test-runs/{run_id}
```

List responses include `X-Total-Count`.

## Debugging Failed Runs

1. Check the terminal run status and `runner_error` event.
2. Expand warning/error timeline rows in the Profile Editor.
3. If `fallback` appears, inspect the reason:
   - `graph_missing_or_unusable`: graph mode lacks a usable graph block.
   - `graph_validation_failed`: backend validator rejected the graph structure.
   - `graph_realtime_fallback`: graph mode cannot run natively under realtime.
4. If a tool issue appears, check `tool_call.tool_config`, `mode`, `timeout_seconds`, `elapsed_ms`, and `timed_out`.
5. If Flow Test passes but voice or LLM behavior fails, debug voice Try/session logs or the future LLM-backed text runner; Flow Test does not cover LLM reasoning, audio, rooms, STT/TTS, telephony, or external side effects.

## Storage

Backend tables:

- `profile_test_runs`
- `profile_test_run_events`

Each run records the profile id, tool mode, status, user message, final summary, profile config hash, and snapshot timestamp. Events are ordered by `seq` and are sanitized before persistence and again before API output.
