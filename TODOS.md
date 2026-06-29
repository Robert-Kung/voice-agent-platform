# TODOS

## Live 語音 e2e follow-up

- **Resolved 2026-06-29**: `elevator_repair_graph` 緊急分支的 `tool_result → handoff` runtime 語意已修。domain tool 回傳後若目標是 handoff node，wrapper 直接委託既有 `transfer_to_human` tool，避免 source node 先生成自由文字；工具結果會注入 handoff 目標 context。
- **Verified**: Try room `test-5f025c0aa3fd438291317001529632d1`：`goto_emergency` → `create_maintenance_ticket` → HTTP timeout → log 立即出現 `transfer_to_human: handing off to HumanOperator_...`；外部 LINE 單據也已由使用者確認收到，測試項目可行。
- **Note**: 外部建單 timeout 目前判斷為測試端網路不穩造成；LINE 單據已收到，暫不列為產品 blocker。

## Next SDD candidate: Test run log + text test

- **Priority**: 先做文字測試與結構化 test run log，再整合語音測試面板。
- **Why now**: Graph agent e2e 已可行；下一步應讓使用者與開發者能看懂每次測試走到哪個 node、觸發哪條 edge、呼叫哪些 tools、是否 handoff。
- **Scope**: 建立文字測試入口、保存 test run/event log、在 Profile Editor 顯示測試結果與 graph path/tool-call 狀態。
- **SDD**: OpenSpec change `profile-test-runs`。

## Graph 編輯器殘項（2026-06-12 /review 低優先）

- **M7 canvas 打字重建**: NodeInspector/Global Prompt 打字每鍵觸發 `GraphCanvas` 的 graph-effect 重建全部 React Flow nodes/edges。<50 節點下毫秒級、無使用者可感差異。若 graph 變大：在 effect 內 merge 未變更節點的舊參照，或讓 prompt-only 編輯跳過重建（`frontend/components/admin/graph-canvas.tsx` 的 useEffect）。
- **L6 style map 跨模組 cast**: `graph-canvas.tsx` 從 `agent-flow-builder.tsx` import NODE_ICONS/COLORS（FlowNodeType keyed），靠 `n.type as FlowNodeType` cast 橋接 GraphNodeType——未來 GraphNodeType 加值時編譯不會抓到 map 缺項。解法：抽 GraphNodeType-keyed 子集到 `frontend/lib/agent-graph-style.ts`，FlowNodeType 回歸純 legacy。

## Graph runtime deferred items（低優先）

- **tool_result ambiguous edge case**: node 同時有條件式 + 無條件 `tool_result` 出邊時，array-order 靜默選一；目前 validator warning 未細分此罕見情境。
- **End node hang-up**: v1 `end` 節點仍會 `generate_reply()` 講一句，不會主動掛電話；可在真實需求出現時補 hang-up semantics。

## Follow-up ideas（未啟動）

- **Per-node model UI**: runtime v1 只留 per-node model spec 介面點，實際仍用 session-level 模型；UI 尚未設計。
- **AI Generate graph draft**: 現有 Generate 支援 prompt create/enhance；描述 → graph nodes/edges 草稿仍是延伸功能。
