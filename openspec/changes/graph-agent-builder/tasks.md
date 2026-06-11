> 2026-06-11 實作備註：§1 純函數/型別實際落在 `frontend/lib/agent-graph.ts`（無 React/Next import，vitest 可直接跑），`use-profile-form.ts` re-export 型別——比塞進 hook 檔更符合 7.1「pure-function scope」。§6 範例為**新檔** `agents/profiles/elevator_repair_graph.yaml`（不動既有 `elevator_repair.yaml`，當時有未 commit 的人工編輯）。7.5 瀏覽器 QA 待 `/qa` 跑 golden path。

## 1. Data model & types (graph-agent-schema)

- [x] 1.1 Add `GraphNode`, `GraphEdge`, `AgentGraph`, and `EditorMode` types in `frontend/hooks/use-profile-form.ts` (node `type`: `start|prompt|end|handoff`, fields `id/type/title/prompt/tools/position`; edge fields `id/source/target/trigger/condition/label`, `trigger: 'user_turn'|'tool_result'` default `user_turn`; `AgentGraph` carries `schema_version: 1`) — NO `variable_keys` (review: dropped from v1)
- [x] 1.2 Extend `KnownConfig` with optional `graph?: AgentGraph` and `editor_mode?: EditorMode`; add `'graph'` and `'editor_mode'` to `KNOWN_KEYS`
- [x] 1.3 Confirm `splitConfig` / `buildConfig` round-trip `graph` + `editor_mode` (free-form, no backend migration); default `editor_mode` to `prompt` when absent
- [x] 1.4 Write `promptToGraph(known)` migration helper: build single `start` node from `instructions` + global tool names; add `handoff` node + edge when `human_operator.enabled`; set `editor_mode='graph'`
- [x] 1.5 Write `graphToPrompt(graph)` flatten helper (review T3): structured serialization of `global_prompt` + node titles/prompts + edge trigger/condition descriptions into a single `instructions` string; called on every graph-mode save so the fallback never goes stale (closes old OQ3, defuses the SIP stale-prompt landmine)
- [x] 1.6 Write `validateGraph(graph, availableTools)` returning errors (no/duplicate `start`, duplicate node id, edge endpoint not found, node unreachable from `start`, edge into `start`, edge out of `end`, invalid `trigger`) and warnings (multiple unconditional out-edges on one source — later ones unreachable under array-order priority, dangling tool reference). Legal tool set = profile `config.tools` names ∪ builtin `availableTools` ∪ `AUTO_MOUNTED_TOOLS` (review D5: `cleanLegacyTools` strips `transfer_to_human`/`lookup_qa` from config.tools, so checking config.tools alone false-positives on the handoff flow itself); skip the tool check when `availableTools` failed to load

## 2. Hook actions (state management)

- [x] 2.1 Add graph actions to `useProfileForm`: `addNode`, `removeNode`, `updateNode`, `setNodePosition`
- [x] 2.2 Add edge actions: `addEdge`, `removeEdge`, `updateEdge` (trigger/condition/label)
- [x] 2.3 Add `setEditorMode` and `convertToGraph` (wraps `promptToGraph`); ensure `isDirty` snapshot includes `graph` + `editor_mode` (position drags marking dirty is accepted — layout is config; review F13)
- [x] 2.4 Wire `validateGraph` into `handleSave`: block on errors, surface warnings via toast/inline; on graph-mode save, regenerate `instructions` via `graphToPrompt` before persisting (task 1.5)

## 3. Editable canvas (graph-editor-ux)

- [x] 3.1 Extend `agent-flow-builder.tsx` with conversation node types `start`/`prompt`/`end`/`handoff` (reuse existing chart-N color tokens + lucide icons); rename the existing hub-and-spoke `FlowNodeType` `'prompt'` to avoid the same-name-different-meaning collision (review D3)
- [x] 3.2 **Controlled-canvas contract (review D3 — implementation precondition, not a UI detail)**: `useProfileForm.known.graph` is the single source of truth; canvas derives nodes/edges from `config.graph` and propagates changes up ONLY on semantic events (connect / node・edge delete / drag-stop / inspector edit), never per-pixel. The current component is a one-way dead end (`useNodesState` reads props once; the declared `onNodesChange`/`onEdgesChange` props are never invoked) — do NOT carry that pattern over; editable mode without upward propagation = silent data loss on save
- [x] 3.3 Make canvas editable when not `readOnly`: node add palette, node/edge delete, `onConnect` creating edges with `trigger: 'user_turn'` + empty `condition`
- [x] 3.4 Persist node `position` back into `graph.nodes` on drag-stop
- [x] 3.5 Update `buildFlowFromConfig` to render directly from `config.graph` when present; keep existing read-only hub-and-spoke projection as fallback for profiles without `graph`

## 4. Node inspector & edge editing

- [x] 4.1 Build Node Inspector panel: edit selected node `title` / `prompt`; when the selected node is `start`, additionally project top-level `welcome_message` / `welcome_instructions` (data stays top-level — review D4: these drive the runtime greeting but their only editor UI lives in the prompt-mode-only `PromptEditor`)
- [x] 4.2 Reuse existing tools UI in the inspector to attach/detach tool names referencing the profile global tools list / builtins (no tool redefinition in node)
- [x] 4.3 Build edge editing UI: select edge → edit `trigger` (user_turn / tool_result dropdown), natural-language `condition`, optional `label`; show label on canvas; edge ordering = priority (array order)
- [x] 4.4 When no node selected, render existing global panels (QA / Hours / Identity / Advanced) + `global_prompt` editor

## 5. Editor mode integration (page)

- [x] 5.1 In `profiles/[id]/page.tsx`, switch center pane between `PromptEditor` (`prompt` mode) and editable `AgentFlowBuilder` (`graph` mode) by `editor_mode`
- [x] 5.2 Add "Convert to graph" action + mode toggle in header; saving after a mode switch requires confirm stating it changes the live runtime strategy source (review F4); switching back to `prompt` labels honestly that the editor shows the latest `graphToPrompt` flatten, not the pre-conversion original (review F15 — "lossless" only holds at conversion instant)
- [x] 5.3 Right panel switches between Node Inspector (node selected) and global settings (deselected)
- [x] 5.4 Graph-mode Try/deploy interim behavior (review D1/T3): runs the auto-regenerated `instructions` fallback; editor shows a persistent banner "目前由 instructions fallback 執行（graph 執行待 graph-runtime-executor）"

## 6. Example profile & docs

- [x] 6.1 Produce a graph version of `elevator_repair` (`start →{緊急, 一般報修, 非報修}→ handoff/end`) as a reference example — must exercise `tool_result` trigger edges (建單成功→轉接、建單失敗→轉接), which is the case that forced the trigger field (review T1)
- [x] 6.2 Ensure `agents/tests/test_agent_system.py` assertions still pass for legacy (no-graph) profiles; sync any assertions if the elevator example replaces existing fields

## 7. Test infrastructure & validation (review D7: frontend currently has NO test runner)

- [x] 7.1 Add vitest to `frontend/` (pure-function scope only — no jsdom, no component testing) with a `test` script in package.json
- [x] 7.2 Unit-test `promptToGraph` (conversion correctness incl. handoff node) and `graphToPrompt` (flatten output, save-regeneration), including edge cases: empty tools, partial `human_operator`, special characters in instructions
- [x] 7.3 Unit-test `validateGraph`: each error/warning case, reachability (disconnected cycle = error), legal tool set union incl. AUTO_MOUNTED_TOOLS, availableTools-load-failure skip
- [x] 7.4 **REGRESSION (critical)**: snapshot test that `buildFlowFromConfig` output for legacy (no-graph) configs is unchanged after the task 3.5 rewrite — only existing behavior this change touches; currently zero coverage
- [ ] 7.5 Frontend build passes (DONE); browser QA (PENDING): add/connect/delete nodes, edit edge trigger/condition, node inspector incl. start-node welcome projection, convert-to-graph + mode-switch confirm round trip, legacy profile still renders preview
- [x] 7.6 Confirm a saved graph profile round-trips through the API (`config_json`) intact with no DB migration, `schema_version: 1` preserved
