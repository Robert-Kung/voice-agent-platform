# Tasks: llm-text-test

## 1. 資料層與 kind 區分

- [ ] 1.1 `profile_test_runs` 加 `kind` 欄位（`flow` | `llm_text`，default `flow`），走 `engine.py _add_missing_columns` migration
- [ ] 1.2 `test_run_store.py` create/list 支援 kind；list API 加 kind filter；event payload `schema_version` 升為 2
- [ ] 1.3 backend tests：kind default 相容（既有 flow test 契約不變）、kind filter

## 2. LLM-only resolver 與共用 helpers

- [ ] 2.1 新增 `resolve_text_test_llm(profile)`：從 `models.llm` spec 建 LLM instance（重用 `providers.py` / `constants.py`），realtime profile 回 fallback LLM + warning flag
- [ ] 2.2 抽出 prompt instructions 組裝共用 helper（與 `create_agent_class()` 同源），graph node instructions 組裝共用 helper（與 `build_graph_root_agent` 同源）
- [ ] 2.3 建 fake LLM（實作 LiveKit `llm.LLM` 介面，可腳本化回覆序列含 tool calls）供測試注入

## 3. Prompt mode LLM runner

- [ ] 3.1 `run_profile_llm_text_test()` prompt path：ChatContext + `llm.chat()` loop、多輪 messages、tool call → dry-run dispatcher → 結果餵回 LLM
- [ ] 3.2 事件記錄：`llm_response`、`tool_call`/`tool_result`、`token_usage`、`test_completed`；全部過 sanitizer
- [ ] 3.3 失敗處理：單輪 timeout、LLM API error → run failed + error 事件，無殭屍 run
- [ ] 3.4 backend tests（fake LLM）：單輪、多輪、tool call 回饋、timeout→failed、realtime fallback warning

## 4. Graph mode text runner

- [ ] 4.1 Graph text runner：node state machine、`user_turn` edge → 合成 `goto_*` tools（description 帶 NL condition，對齊 runtime `generation.py`）、`tool_result` edge 無條件轉移
- [ ] 4.2 終止條件：handoff / end node / `max_steps`；final summary 含 graph path 與終止原因
- [ ] 4.3 graph 驗證失敗 / 缺 graph → warning + fallback prompt path（沿用 flow test fallback 語意）
- [ ] 4.4 backend tests（fake LLM）：goto 路由、tool_result 轉移、max_steps 截斷、fallback、與 runtime tool schema 一致性 assert

## 5. API 擴充

- [ ] 5.1 `schemas.py` / `routes_profile_test_runs.py`：request 加 `kind` 與 `messages[]`（單 `message` 相容）、response 含 kind 與 usage summary
- [ ] 5.2 backend tests：POST llm_text run（fake LLM 注入）、未帶 kind 走 flow、list kind filter、auth

## 6. Frontend

- [ ] 6.1 `admin-api.ts`：kind / messages / usage types 與 API calls
- [ ] 6.2 Panel 分 Flow Test / Text Test（tab 或 mode switch）：Text Test 支援多輪輸入、顯示 LLM 回覆 / tool calls / graph path / usage、明示 token 花費；recent runs 標示 kind
- [ ] 6.3 frontend tests：helpers（usage 彙總、kind 標示、event 呈現）與 API client

## 7. 驗證與文件

- [ ] 7.1 Gated integration test：`LLM_TEXT_TEST_INTEGRATION=1` 打真實 LLM 跑 prompt + graph 各一輪，CI 預設 skip
- [ ] 7.2 全套測試綠燈：`cd agents && uv run pytest tests/ -q`、`cd frontend && pnpm test`、`pnpm exec tsc --noEmit`
- [ ] 7.3 瀏覽器 QA：prompt profile 與 graph profile 各跑一次 Text Test，確認 LLM 回覆與 graph path 呈現
- [ ] 7.4 文件同步：docs/TEXT_TEST_GUIDE.md 補 Text Test 章節（與 Flow Test 差異、成本注意）、TODOS.md / CLAUDE.md 更新
