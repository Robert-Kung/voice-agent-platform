<!-- /autoplan restore point: /home/user/.gstack/projects/Robert-Kung-first-livekit/main-autoplan-restore-20260629-163950.md -->

## 1. Backend Data Model And Store

- [ ] 1.1 Add profile test run and test run event persistence models with profile id, status, tool execution mode, timestamps, final summary, event order, event type, severity, and JSON payload.
- [ ] 1.2 Include profile config hash, snapshot timestamp, event payload `schema_version`, and finite run statuses (`created`, `running`, `completed`, `failed`, `cancelled`).
- [ ] 1.3 Add store helpers to create runs, append ordered events, finalize run status, retrieve a run with events, and list recent runs by profile with `limit`/`offset` plus total count or `has_more`.
- [ ] 1.4 Add allowlist-first payload sanitization utilities that redact secrets, authorization headers, query-string credentials, and sensitive environment-derived values before storing or returning events.

## 2. Text Test Runner

- [ ] 2.1 Implement a profile text-test service that loads saved profiles and applies the same normalization, graph validation, and strategy-source gate used by runtime.
- [ ] 2.2 Implement prompt-mode text test execution that records user input, assistant output or placeholder output, warnings/errors, and run completion.
- [ ] 2.3 Implement graph-mode text test execution for node entry, user-turn edge selection, tool-result transition logging, handoff events, and fallback warnings when graph execution is unavailable.
- [ ] 2.4 Implement a central test-run tool dispatcher for `dry_run` and `live` modes, including planned-call events, side-effect suppression, mode labeling, and consistent tool result shapes.
- [ ] 2.5 Enforce text-run and per-tool timeouts, recording timeout events with tool name, mode, and elapsed duration.
- [ ] 2.6 Record that text test graph paths are the path taken by this run and do not replace voice Try validation.

## 3. Admin API

- [ ] 3.1 Add authenticated `POST /api/profiles/{profile_id}/test-runs` endpoint with message and `tool_execution_mode: dry_run | live = dry_run`.
- [ ] 3.2 Add authenticated `GET /api/profiles/{profile_id}/test-runs/{run_id}` endpoint to retrieve a test run with ordered sanitized events.
- [ ] 3.3 Add authenticated `GET /api/profiles/{profile_id}/test-runs?limit=50&offset=0` endpoint with profile scoping and total count or `has_more` metadata.
- [ ] 3.4 Define response schemas for run summaries, event rows, list responses, and error responses that include `run_id` when partial events exist.
- [ ] 3.5 Ensure API errors preserve run events where possible and return user-readable failure reasons.

## 4. Profile Editor UI

- [ ] 4.1 Add a compact text test panel to the Profile Editor with message input, tool execution mode selector, run button, and loading/error states.
- [ ] 4.2 Render run summary, final assistant output, warnings, errors, handoff outcome, and text-test-vs-voice-Try caveat.
- [ ] 4.3 Render ordered event timeline rows with timestamp, type, severity, mode/status badges, accessible expand/collapse controls, and sanitized payload details.
- [ ] 4.4 Render graph-mode visited path and edge/tool-call states, distinguishing conditional edges, tool-result edges, dry-run, live, success, timeout, and error outcomes.
- [ ] 4.5 Add fallback warning banner when graph execution degrades to flattened prompt mode.
- [ ] 4.6 Add recent-run loading for the current profile with a default bounded count and a selector to inspect the latest runs without leaving the editor.
- [ ] 4.7 Verify responsive behavior and keyboard navigation for the compact panel and timeline controls.

## 5. Tests And Validation

- [ ] 5.1 Add backend tests for run creation, event ordering, auth enforcement, fallback warning events, and retrieval/list APIs.
- [ ] 5.2 Add backend tests for status transitions, profile snapshot/config hash recording, event schema versioning, and API pagination metadata.
- [ ] 5.3 Add backend tests proving default dry-run tools do not call external HTTP endpoints and live mode records live tool metadata.
- [ ] 5.4 Add backend tests proving sanitization redacts nested headers, query credentials, token/password/secret keys, and environment-derived values before persistence/API response.
- [ ] 5.5 Add fixture-based graph text tests for a `user_turn` transition and a `tool_result` transition.
- [ ] 5.6 Add frontend tests for starting a text run, rendering event timelines, graph path/tool states, tool mode badges, fallback warning banner, and API error states.
- [ ] 5.7 Run `cd agents && uv run pytest tests/ -q` and `cd frontend && pnpm test`.

## 6. Documentation And QA

- [ ] 6.1 Add `docs/TEXT_TEST_GUIDE.md` covering time-to-first-test, event types, tool modes, dry-run safety, graph-vs-voice differences, and debugging failed tests.
- [ ] 6.2 Update project docs or TODO notes with the new text-test workflow and dry-run/live tool behavior.
- [ ] 6.3 Manually verify the Profile Editor text test panel on a graph profile and a prompt profile.
- [ ] 6.4 Manually verify that voice Try remains available and is clearly separate from text tests.

## GSTACK REVIEW REPORT

### Autoplan Status

DONE_WITH_CONCERNS. Reviewed the OpenSpec change through CEO, design, engineering, and DX lenses. Codex CLI was unavailable in this environment, so dual voice review degraded to Claude subagent-only.

### Plan Summary

The plan targets the right next product problem: after graph e2e became viable, profile authors need a fast text-first test loop with structured event logs before they run voice Try. The original direction stands, but the implementation contract needed sharper API, tool safety, event schema, and UI-state detail before build.

### Scope Detection

- UI scope: yes. The Profile Editor adds a compact text test panel, event timeline, graph path state, and tool mode controls.
- DX scope: yes. The change introduces admin APIs, error surfaces, docs, and a developer/admin debug workflow.
- Voice integration scope: explicitly not replacing voice Try.

### CEO Review

Assessment: correct next problem, good scope boundaries, medium strategic risk.

Findings:
- Text tests must be framed as authoring/debug checks, not proof that voice, STT/TTS, SIP, or external integrations work.
- Dry-run tools can create false confidence unless live mode and voice Try remain visible.
- Graph runtime stability and graph/text divergence are the main six-month risks.

Auto-decisions:
- Keep text tests as the next feature, because it shortens the authoring loop without replacing voice e2e.
- Add explicit text-vs-voice caveat to spec and UI tasks.
- Keep voice Try separate and visible as final integration validation.

### Design Review

Assessment: good interaction direction, but original UI tasks were under-specified.

Findings:
- Tool mode clarity was too weak. Users need to see `dry_run` or `live` before and after a run.
- Graph path visualization needed concrete event/timeline behavior.
- Timeline rows needed expand/collapse, timestamps, badges, sanitized details, and keyboard support.
- Fallback warnings need banner-level visibility, not only buried timeline events.

Auto-decisions:
- Expand UI tasks for status badges, accessible timeline rows, graph path/edge states, fallback banners, responsive behavior, and keyboard navigation.
- Keep the panel compact by putting detailed timeline and recent runs behind expandable UI.

### Engineering Review

Assessment: architecture is viable after tightening three contracts.

Findings:
- Dry-run semantics cannot live as ad hoc branches in individual tools; they need a central dispatcher.
- Event sanitization must be allowlist-first and happen before persistence and API response.
- Text runner must avoid pretending LiveKit handoff is happening; handoff should be represented as events.
- Profile config must be snapshotted or hash-recorded when the run starts.
- Tool timeouts, status transitions, pagination, and event schema versioning needed to be explicit.

Auto-decisions:
- Add central test-run tool dispatcher task.
- Add `schema_version: 1`, finite run statuses, profile config hash, snapshot timestamp, timeout events, and pagination metadata.
- Preserve partial events on runner failure where possible.

### DX Review

Assessment: strong concept, weak original API contract.

Findings:
- API routes, methods, response schemas, status codes, and error shape needed to be concrete.
- Existing API conventions favor profile-scoped routes and `limit`/`offset` list behavior.
- Documentation needs a text test guide, not a buried TODO note.

Auto-decisions:
- Use `POST /api/profiles/{profile_id}/test-runs`, `GET /api/profiles/{profile_id}/test-runs`, and `GET /api/profiles/{profile_id}/test-runs/{run_id}`.
- Add response schema and error response tasks, including `run_id` when partial events exist.
- Add `docs/TEXT_TEST_GUIDE.md` to the implementation checklist.

### Cross-Phase Themes

- Tool mode safety appeared in CEO, design, engineering, and DX review. High-confidence requirement: `dry_run` must be safe by default and visually obvious.
- Text-vs-voice divergence appeared in CEO, engineering, and DX review. High-confidence requirement: text tests are for authoring/debug, voice Try remains final validation.
- Event schema clarity appeared in design, engineering, and DX review. High-confidence requirement: typed, versioned, sanitized event payloads are part of the product contract, not an implementation detail.

### User Challenges

None. The review did not recommend changing the user's stated direction. It recommended tightening the implementation contract before build.

### Taste Decisions

None surfaced for user approval. All changes were mechanical completeness fixes inside the requested scope.

### Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|----------------|-----------|-----------|----------|
| 1 | CEO | Keep text test + test run log as next feature | Mechanical | Completeness | It directly solves the current authoring/debug bottleneck after graph e2e became viable | Defer in favor of per-node models or AI graph generation |
| 2 | CEO | Add text-vs-voice caveat | Mechanical | Explicit over clever | Prevents authors from treating text tests as external integration proof | Silent assumption that text pass means deploy-safe |
| 3 | Design | Make tool mode visible before and after run | Mechanical | Completeness | Prevents confusion and duplicate external side effects | Hidden dry-run/live state |
| 4 | Design | Add accessible expandable timeline rows | Mechanical | Completeness | Lets compact UI still expose inspectable event detail | Raw log dump or always-expanded payloads |
| 5 | Eng | Centralize dry-run/live tool dispatch | Mechanical | DRY | Prevents inconsistent per-tool dry-run semantics | Ad hoc tool-level dry-run branches |
| 6 | Eng | Add schema versioning and allowlist-first sanitization | Mechanical | Completeness | Protects old runs and prevents secret leakage | Unversioned payloads and blocklist-only redaction |
| 7 | Eng | Snapshot profile config hash at run creation | Mechanical | Explicit over clever | Makes historical run results explainable after profile edits | Always interpret runs against latest profile |
| 8 | DX | Use profile-scoped test-run API routes | Mechanical | DRY | Aligns with existing admin API shape and profile ownership | Global `/api/test-runs?profile_id=` surface |
| 9 | DX | Add `docs/TEXT_TEST_GUIDE.md` | Mechanical | Completeness | Reduces onboarding and support burden for text-vs-voice/tool-mode behavior | Rely only on UI hints |

### Review Scores

- CEO: 8/10. Right problem and scope; medium risk around false confidence.
- Design: 7/10 before revisions, 8/10 after revisions. Main gaps were UI-state specificity and mode clarity.
- Engineering: 6/10 before revisions, 8/10 after revisions. Main blockers were dry-run protocol, sanitization, and status/event contracts.
- DX: 6/10 before revisions, 8/10 after revisions. Main blockers were route/schema/error-contract specificity.

### Deferred To Future Scope

- Multi-turn conversational test sessions.
- Deterministic path override UI for graph tests.
- Production session observability and text-vs-voice route-drift analytics.
- Replay editor or full standalone test run analysis page.

### Implementation Guidance

Start with data model, event schema, sanitizer, and API contracts before UI. The UI depends on stable event payloads, status values, and tool mode semantics; building the panel first would lock in the wrong abstractions.