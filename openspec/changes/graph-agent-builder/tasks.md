## 1. Data model & types (graph-agent-schema)

- [ ] 1.1 Add `GraphNode`, `GraphEdge`, `AgentGraph`, and `EditorMode` types in `frontend/hooks/use-profile-form.ts` (`type`: `start|prompt|end|handoff`; node fields `id/type/title/prompt/tools/variable_keys/position`; edge fields `id/source/target/condition/label`)
- [ ] 1.2 Extend `KnownConfig` with optional `graph?: AgentGraph` and `editor_mode?: EditorMode`; add `'graph'` and `'editor_mode'` to `KNOWN_KEYS`
- [ ] 1.3 Confirm `splitConfig` / `buildConfig` round-trip `graph` + `editor_mode` (free-form, no backend migration); default `editor_mode` to `prompt` when absent
- [ ] 1.4 Write `promptToGraph(known)` migration helper: build single `start` node from `instructions` + global tool names; add `handoff` node + edge when `human_operator.enabled`; set `editor_mode='graph'`; preserve original `instructions`
- [ ] 1.5 Write `validateGraph(graph)` returning errors (no/duplicate `start`, duplicate node id, edge endpoint not found) and warnings (isolated node, empty condition on multi-out-edge node, dangling tool reference)

## 2. Hook actions (state management)

- [ ] 2.1 Add graph actions to `useProfileForm`: `addNode`, `removeNode`, `updateNode`, `setNodePosition`
- [ ] 2.2 Add edge actions: `addEdge`, `removeEdge`, `updateEdge` (condition/label)
- [ ] 2.3 Add `setEditorMode` and `convertToGraph` (wraps `promptToGraph`); ensure `isDirty` snapshot includes `graph` + `editor_mode`
- [ ] 2.4 Wire `validateGraph` into `handleSave`: block on errors, surface warnings via toast/inline before persisting

## 3. Editable canvas (graph-editor-ux)

- [ ] 3.1 Extend `agent-flow-builder.tsx` node types with `start`/`prompt`/`end`/`handoff` custom nodes (reuse existing chart-N color tokens + lucide icons)
- [ ] 3.2 Make canvas editable when not `readOnly`: enable `onNodesChange`/`onEdgesChange`, `onConnect` creating edges with empty `condition`, node add palette, node/edge delete
- [ ] 3.3 Persist node `position` back into `graph.nodes` on drag-stop
- [ ] 3.4 Update `buildFlowFromConfig` to render directly from `config.graph` when present; keep existing read-only hub-and-spoke projection as fallback for profiles without `graph`

## 4. Node inspector & edge editing

- [ ] 4.1 Build Node Inspector panel: edit selected node `title` / `prompt` / `variable_keys`
- [ ] 4.2 Reuse existing tools UI in the inspector to attach/detach tool names referencing the profile global tools list (no tool redefinition in node)
- [ ] 4.3 Build edge editing UI: select edge → edit natural-language `condition` + optional `label`; show label on canvas
- [ ] 4.4 When no node selected, render existing global panels (QA / Hours / Identity / Advanced) + `global_prompt` editor

## 5. Editor mode integration (page)

- [ ] 5.1 In `profiles/[id]/page.tsx`, switch center pane between `PromptEditor` (`prompt` mode) and editable `AgentFlowBuilder` (`graph` mode) by `editor_mode`
- [ ] 5.2 Add "Convert to graph" action + mode toggle in header; show active-source indication when in graph mode
- [ ] 5.3 Right panel switches between Node Inspector (node selected) and global settings (deselected)
- [ ] 5.4 Handle graph-mode Try/deploy degradation pending runtime support (see open question 1) — surface clear messaging rather than silently failing

## 6. Example profile & docs

- [ ] 6.1 Produce a graph version of `elevator_repair` (`start →{緊急, 一般報修, 非報修}→ handoff/end`) as a reference example
- [ ] 6.2 Ensure `agents/tests/test_agent_system.py` assertions still pass for legacy (no-graph) profiles; sync any assertions if the elevator example replaces existing fields

## 7. Validation & QA

- [ ] 7.1 Unit-test `promptToGraph` (lossless, reversible) and `validateGraph` (each error/warning case)
- [ ] 7.2 Frontend build passes; browser QA: add/connect/delete nodes, edit edge condition, node inspector, convert-to-graph round trip, legacy profile still renders preview
- [ ] 7.3 Confirm a saved graph profile round-trips through the API (`config_json`) intact with no DB migration
