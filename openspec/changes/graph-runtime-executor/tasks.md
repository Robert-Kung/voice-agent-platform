## 1. 後端 validator（gate 的共同依賴，先上）

- [x] 1.1 新增 `agents/runtime/graph.py`，實作 `validate_graph(graph, available_tools, config_tool_names, *, handoff_enabled, mode)`，回傳 `errors` / `warnings` / `valid`（結構對齊前端 `validateGraph`）
- [x] 1.2 實作全部 error 規則：唯一 start、node id/edge id 不重複、合法 node type、edge 端點存在、no edge into start、no edge out of end、合法 trigger、從 start BFS 可達性
- [x] 1.3 mode 耦合 error：`editor_mode: graph` + `models.mode: realtime` → blocking error（graph 與 realtime 互斥）
- [x] 1.4 實作全部 warning 規則：self-loop、同 `(source, trigger)` 多條無條件出邊、dangling tool、handoff node 但 handoff 未啟用、**tool_result 邊帶非空 condition**（v1 不支援，當無條件）
- [x] 1.5 加 normalize 防禦：config 是 free-form JSON，validator 入口須容忍缺欄位（對齊前端 `normalizeGraph` 的 load-boundary 行為）
- [x] 1.6 `agents/tests/` 補 validator 單元測試，逐條覆蓋 spec 的 scenario（含 parity case：與前端規則相同輸入相同判定）

## 2. API 存檔硬驗證 + mode 阻擋

- [x] 2.1 `agents/api/routes_profiles.py` 的 create/update：config 帶 `editor_mode: graph` 時，存檔前跑 `validate_graph`，有 blocking error（含 graph+realtime 互斥）回 HTTP 422（不持久化）
- [x] 2.2 `editor_mode: prompt` 或無 graph block 的存檔維持 passthrough，不跑結構驗證
- [x] 2.3 補 API 測試：invalid graph-mode save → 422、graph+realtime → 422、valid graph+pipeline → 持久化、prompt-mode → bypass
- [x] 2.4 前端編輯器：graph mode 顯示「需 pipeline 部署」提示（agent mode 在編輯器不可改、無 toggle 可 disable；後端 422 才是強制 gate）

## 3. 策略來源 gate 與 fallback

- [x] 3.1 `agent_factory` 新增 `build_root_agent`（gate）+ `_select_graph_strategy`：`editor_mode == 'graph'` AND `validate_graph().valid` AND `mode == 'pipeline'` → graph 組裝；否則單一 instructions（`create_agent_class` 不動）
- [x] 3.2 fallback 一律不 raise（含 graph 組裝 exception），warning log 標明原因（非 graph mode / validator 失敗 / realtime mode）
- [x] 3.3 補測試：三種 fallback 路徑各自落到 instructions 路徑；prompt-mode profile 行為不變（`test_graph_runtime.py`）

## 4. Graph 執行組裝（node → Agent + handoff）

- [x] 4.1 global preamble 組裝：`global_prompt` + QA inline block + services hours block（沿用 `_render_qa_block` / `_render_services_block`），前置到每個 node instructions
- [x] 4.2 per-node Agent builder：instructions = global preamble + node `prompt`；tools = node `tools` 經三層掛載規則解析；`qa_mode == tool` 時每個 node 掛 `lookup_qa`
- [x] 4.3 user_turn 出邊 → 生成 handoff function_tool，description 反映 `condition`，回傳 target node Agent；空 condition = 無條件邊，反映在 instructions；多邊依 `edges` 陣列順序生成
- [x] 4.4 tool_result 出邊 → 包裝 node domain tool 回傳 `(result, target Agent)`（SDK handoff，保留參數 schema），v1 一律無條件、首邊優先；非空 condition 不實作（validator 已 warning）
- [x] 4.5 `handoff` node 啟動 → 掛 `transfer_to_human`，node `prompt` 作 per-handoff greeting；`transfer_to_human` 不全域無條件掛載（僅 handoff node）
- [x] 4.6 `start` node Agent 設為 session 初始 agent（`session.start(agent=root_agent)` 接點）
- [x] 4.7 per-node 模型介面點：node 宣告 model spec 時 log 並 fallback 到 session-level 模型（v1 只留呼叫點，`Agent(llm=/tts=/stt=)` 已驗證可接）

## 5. 整合與驗證

- [x] 5.1 `agents/agent.py entrypoint`：改用 `build_root_agent`；graph-mode pipeline 走新組裝、其餘 profile 行為不變（244 tests green）
- [ ] 5.2 用 `elevator_repair_graph` 跑端到端：start → 情境 → 建單 tool → tool_result 立即轉接。**靜態組裝已驗證**（gate 選 graph、6 nodes、transition 工具齊備）；**live 語音 e2e 待人工**（瀏覽器 Try button，需真實 LiveKit audio session）
- [x] 5.3 `cd agents && uv run pytest tests/ -q` 全綠（244 passed，含 graph validator + runtime 新測試）
- [x] 5.4 更新 `CLAUDE.md`：補 graph 執行 runtime 架構段（gate 條件、pipeline-only 邊界、handoff 組裝）
- [x] 5.5 `openspec validate graph-runtime-executor --strict` 通過（archive 待 5.2 live e2e 完成後執行）

## 6. Code review 修復（子 Agent review）

- [x] 6.1 **#1 死轉移**：node 有 tool_result 出邊但無 domain 工具 → 該轉移永不觸發。新增 `tool_result_no_tool` warning（後端 `validate_graph` + 前端 `validateGraph` parity，雙邊測試）
- [x] 6.2 **#3 nit**：runtime gate 的 `validate_graph(mode=...)` 永遠是 pipeline，加註解澄清 conflict 規則只在 save 路徑生效
- [ ] 6.3 **#2 殘項（defer）**：node 同時有條件式 + 無條件 tool_result 出邊時，array-order 靜默選一、`ambiguous_unconditional` 不涵蓋——罕見，待真實案例
- [ ] 6.4 **#5 殘項（defer）**：補一條顯式測試命名「user_turn + tool_result 同 node 工具 key 不衝突」的不變式（目前由 fixture 隱含覆蓋）
