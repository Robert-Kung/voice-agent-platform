## 1. 後端 validator（gate 的共同依賴，先上）

- [ ] 1.1 新增 `agents/runtime/graph.py`，實作 `validate_graph(graph, available_tools, config_tool_names, *, handoff_enabled, mode)`，回傳 `errors` / `warnings` / `valid`（結構對齊前端 `validateGraph`）
- [ ] 1.2 實作全部 error 規則：唯一 start、node id/edge id 不重複、合法 node type、edge 端點存在、no edge into start、no edge out of end、合法 trigger、從 start BFS 可達性
- [ ] 1.3 mode 耦合 error：`editor_mode: graph` + `models.mode: realtime` → blocking error（graph 與 realtime 互斥）
- [ ] 1.4 實作全部 warning 規則：self-loop、同 `(source, trigger)` 多條無條件出邊、dangling tool、handoff node 但 handoff 未啟用、**tool_result 邊帶非空 condition**（v1 不支援，當無條件）
- [ ] 1.5 加 normalize 防禦：config 是 free-form JSON，validator 入口須容忍缺欄位（對齊前端 `normalizeGraph` 的 load-boundary 行為）
- [ ] 1.6 `agents/tests/` 補 validator 單元測試，逐條覆蓋 spec 的 scenario（含 parity case：與前端規則相同輸入相同判定）

## 2. API 存檔硬驗證 + mode 阻擋

- [ ] 2.1 `agents/api/routes_profiles.py` 的 create/update：config 帶 `editor_mode: graph` 時，存檔前跑 `validate_graph`，有 blocking error（含 graph+realtime 互斥）回 HTTP 422（不持久化）
- [ ] 2.2 `editor_mode: prompt` 或無 graph block 的存檔維持 passthrough，不跑結構驗證
- [ ] 2.3 補 API 測試：invalid graph-mode save → 422、graph+realtime → 422、valid graph+pipeline → 持久化、prompt-mode → bypass（用 `secured_client`）
- [ ] 2.4 前端編輯器：graph mode 時 disable realtime mode 切換（UX 提示，後端 422 才是強制 gate）

## 3. 策略來源 gate 與 fallback

- [ ] 3.1 `agent_factory.create_agent_class` 加分流：`editor_mode == 'graph'` AND `validate_graph().valid` AND `mode == 'pipeline'` → 走 graph 組裝；否則現有單一 instructions 路徑
- [ ] 3.2 fallback 一律不 raise，warning log 標明原因（非 graph mode / validator 失敗 / realtime mode）
- [ ] 3.3 補測試：三種 fallback 路徑各自落到 instructions 路徑且不丟 call；prompt-mode profile 行為不變

## 4. Graph 執行組裝（node → Agent + handoff）

- [ ] 4.1 global preamble 組裝：`global_prompt` + QA inline block + services hours block（沿用 `_render_qa_block` / `_render_services_block`），前置到每個 node instructions
- [ ] 4.2 per-node Agent builder：instructions = global preamble + node `prompt`；tools = node `tools` 經三層掛載規則解析；`qa_mode == tool` 時每個 node 掛 `lookup_qa`
- [ ] 4.3 user_turn 出邊 → 生成 handoff function_tool，docstring 反映 `condition`，回傳 target node Agent；空 condition = 無條件邊，反映在 instructions；多邊依 `edges` 陣列順序生成
- [ ] 4.4 tool_result 出邊 → node domain tool 直接回傳 target Agent（SDK handoff），v1 一律無條件、多邊依陣列順序；非空 condition 不實作（validator 已 warning）
- [ ] 4.5 `handoff` node 啟動 → 呼叫 `transfer_to_human`，node `prompt` 作 per-handoff greeting；`transfer_to_human` 不全域無條件掛載
- [ ] 4.6 `start` node Agent 設為 session 初始 agent（`session.start(agent=...)` 接點）
- [ ] 4.7 per-node 模型介面點：node 宣告 model spec 時呼叫 `runtime/providers.py` 同組 `build_*`，cost 走 session row 可擴充模型名結構；v1 可只留呼叫點 + fallback 到 session-level 模型

## 5. 整合與驗證

- [ ] 5.1 `agents/agent.py entrypoint`：確認 graph-mode pipeline profile 走新組裝、其餘 profile 行為不變
- [ ] 5.2 用 `elevator_repair`（graph 範例 profile）跑端到端：start → 情境 → 建單 tool → tool_result 立即轉接的完整路徑
- [ ] 5.3 `cd agents && uv run pytest tests/ -q` 全綠（含 1-4 新增測試）
- [ ] 5.4 更新 `CLAUDE.md`：補 graph 執行的 runtime 架構段（gate 條件、pipeline-only 邊界、handoff 組裝）
- [ ] 5.5 `openspec validate graph-runtime-executor --strict` 通過，準備 `/opsx:archive`
