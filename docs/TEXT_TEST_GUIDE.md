# Profile Text Test Guide

The Profile Editor's right-side test panel supports two run kinds:

- **Flow Test**（`kind: flow`，預設）：deterministic，不打 LLM，驗證已存 prompt/graph 的 wiring。
- **LLM Text Test**（`kind: llm_text`）：打真實 LLM 的文字對話測試（有 token 成本），不啟 LiveKit room、不用語音、不執行外部工具副作用。

## Flow Test

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

Every event payload includes `schema_version: 2`.

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

LLM Text Test additional event types:

| Event | Meaning |
|---|---|
| `llm_response` | Real LLM reply for a turn (`turn`, `text`, graph mode adds `node_id`) |
| `token_usage` | Per-LLM-call token counts (`prompt_tokens` / `completion_tokens` / `total_tokens`) |
| `llm_fallback` | Realtime profile degraded to the default pipeline LLM for the text run |
| `max_steps_reached` | Runner hit the per-run tool-loop guard (default 10 steps) |

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

LLM Text Test run (multi-turn):

```http
POST /api/profiles/{profile_id}/test-runs
Content-Type: application/json

{
  "kind": "llm_text",
  "messages": ["你好", "電梯壞了，請幫我報修"],
  "tool_execution_mode": "dry_run"
}
```

```http
GET /api/profiles/{profile_id}/test-runs?limit=50&offset=0&kind=llm_text
GET /api/profiles/{profile_id}/test-runs/{run_id}
```

List responses include `X-Total-Count`. `kind` filter is optional (`flow` | `llm_text`).

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

Each run records the profile id, run kind, tool mode, status, user message(s), final summary, profile config hash, and snapshot timestamp. Events are ordered by `seq` and are sanitized before persistence and again before API output.

## LLM Text Test

Select the `LLM Text` tab in the panel. Input is one user message per line; each line becomes one conversation turn.

What it does:

- Resolves the profile's LLM spec (`models.llm`) and runs a real multi-turn text conversation — no LiveKit room, no STT/TTS.
- Prompt profiles use the same composed system instructions as the runtime agent (`compose_prompt_instructions`).
- Graph profiles run a graph text runner: node routing is decided by real LLM tool calls via synthetic `goto_*` transition tools (same names/descriptions as the runtime handoff tools); `tool_result` edges transition unconditionally and the target node replies with the tool result in context; handoff / end nodes terminate the run.
- Tool calls go through the dry-run dispatcher — the structured dry-run result is fed back to the LLM, external side effects are suppressed.
- Realtime profiles fall back to the default pipeline LLM with an `llm_fallback` warning banner — replies may differ from production Gemini Live behavior.

Cost & guards:

- Real LLM tokens are consumed; the final summary and `token_usage` events record usage, shown as badges in the panel.
- Per-turn timeout is 30s; the per-run tool loop stops at `max_steps` (default 10) with a `max_steps_reached` warning.
- LLM reply text is stored after pattern-based credential redaction (`sanitize_llm_text`); structured payloads still pass the key-based sanitizer.

Still not covered (use voice Try): audio, STT/TTS, LiveKit rooms/handoffs, SIP/browser integration, real external tool side effects, realtime-model behavior.

A gated integration test hits a real LLM when `LLM_TEXT_TEST_INTEGRATION=1` is set; CI skips it by default.
