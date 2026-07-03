# Spec Delta: profile-llm-text-test (llm-text-test)

## ADDED Requirements

### Requirement: LLM text test run creation

系統 SHALL 提供 LLM-backed 文字測試：對已存 profile 以真實 LLM 執行文字對話，透過既有 test-runs API 建立 `kind: llm_text` 的 run，並持久化 run 與 ordered events。

#### Scenario: Prompt mode 單輪測試

- **WHEN** 對 `editor_mode: prompt` 的 profile 建立 llm_text run 帶單一 user message
- **THEN** runner 以 profile 的 LLM 設定建立 LLM-only client（不建 STT/TTS、不開 LiveKit room），用與 runtime 相同的 instructions 組裝呼叫 LLM，並記錄 `test_started`、`prompt_rendered`、`llm_response`（含真實 LLM 回覆文字）、`test_completed` 事件

#### Scenario: 多輪 messages 依序執行

- **WHEN** run request 帶多則 user messages
- **THEN** runner 依序執行每輪對話並保留 chat context，每輪各記錄一個 `llm_response` 事件，事件標示輪次

#### Scenario: LLM 呼叫失敗或逾時

- **WHEN** LLM 呼叫拋錯或超過單輪 timeout
- **THEN** run 以 `failed` 結束並記錄 `error` 事件（sanitized），不留下 `running` 狀態的殭屍 run

### Requirement: Graph mode LLM 路由

`editor_mode: graph` 且 graph 驗證通過的 profile，llm_text run SHALL 以 graph text runner 執行：每個 node 的 instructions 與 runtime 相同組裝，`user_turn` edges 轉為合成 `goto_*` transition tools 交由 LLM 判斷，`tool_result` edges 在 domain tool 回傳後無條件轉移。

#### Scenario: LLM 呼叫 goto 工具觸發轉移

- **WHEN** LLM 在某 node 呼叫 `goto_<target>` 合成工具
- **THEN** runner 記錄 `edge_selected` 與 `node_entered` 事件並在 target node 繼續對話

#### Scenario: tool_result edge 轉移

- **WHEN** LLM 呼叫的 domain tool 所在 node 有 `tool_result` edge
- **THEN** runner 在工具回傳後記錄 `tool_result` 與轉移事件，進入 target node

#### Scenario: 終止條件

- **WHEN** 對話進入 handoff node、end node，或步數達 `max_steps` 上限
- **THEN** runner 結束 run 並在 final summary 記錄 graph path 與終止原因

#### Scenario: Graph 驗證失敗 fallback

- **WHEN** graph 缺失或後端驗證失敗
- **THEN** runner 記錄 warning 事件並 fallback 至 prompt mode 文字測試（flatten instructions），run 不失敗

### Requirement: 工具 dry-run 語意

llm_text run 中 LLM 呼叫 domain tools 時，系統 SHALL 以 dry-run dispatcher 回傳合成的 planned-call 結果餵回 LLM，MUST NOT 觸發外部副作用；tool call 與合成結果 SHALL 記錄為 sanitized 事件。

#### Scenario: LLM 呼叫 HTTP domain tool

- **WHEN** LLM 對帶 HTTP endpoint 的 domain tool 發出 tool call
- **THEN** 系統不發出真實 HTTP 請求，記錄 `tool_call` 事件（endpoint 等機密欄位 sanitized），並將合成 dry-run 結果回饋給 LLM 繼續生成

### Requirement: Realtime profile fallback

`models.mode: realtime` 的 profile 執行 llm_text run 時，系統 SHALL NOT 建立 Gemini Live realtime session，SHALL 改用 pipeline 預設 LLM 執行並記錄 warning 事件說明 fallback。

#### Scenario: Realtime profile 執行文字測試

- **WHEN** 對 realtime mode profile 建立 llm_text run
- **THEN** runner 以 fallback LLM 完成測試，事件中含 warning 說明「以 fallback LLM 執行，非 realtime 模型」，run 正常 completed

### Requirement: Run kind 區分與 API 相容

系統 SHALL 以 `kind` 欄位（`flow` | `llm_text`）區分兩種 run；既有 Flow Test API 契約 MUST 保持不變（未帶 kind 的既有 request 預設為 flow）。

#### Scenario: 建立 llm_text run

- **WHEN** POST test-runs 帶 `kind: llm_text`
- **THEN** 系統建立並執行 LLM-backed run，detail response 含 kind 欄位

#### Scenario: 既有 flow test 不受影響

- **WHEN** POST test-runs 未帶 kind（既有契約）
- **THEN** 系統執行 deterministic flow test，行為與 `profile-test-runs` 規格一致

#### Scenario: List 依 kind 過濾

- **WHEN** GET test-runs list 帶 kind query 參數
- **THEN** 僅回傳該 kind 的 runs

### Requirement: 事件 sanitization 與 usage 記錄

llm_text run 的所有事件 payload（含 LLM 回覆文字、tool call 參數）SHALL 經既有 sanitizer 處理後才持久化；LLM API 有回報 usage 時 SHALL 記錄 token usage 事件。

#### Scenario: LLM 回覆含機密樣式內容

- **WHEN** LLM 回覆或 tool call payload 含符合機密樣式的欄位（如 token、api_key）
- **THEN** 持久化的事件 payload 中該值為 `<redacted>`

#### Scenario: Token usage 記錄

- **WHEN** LLM provider 回報 token usage
- **THEN** run 事件含 usage 資訊（prompt/completion tokens），final summary 彙總全 run usage

### Requirement: Profile Editor Text Test UI

Profile Editor 的測試 panel SHALL 區分 Flow Test（deterministic）與 Text Test（LLM-backed），Text Test 檢視 SHALL 呈現真實 LLM 回覆、tool calls、graph path 與 usage，並明示會產生 LLM token 花費。

#### Scenario: 執行 Text Test

- **WHEN** 使用者在 panel 切至 Text Test 並送出 message(s)
- **THEN** UI 建立 llm_text run，顯示 LLM 真實回覆、tool call 事件、graph path（graph profile）與 usage 摘要

#### Scenario: 兩種測試並存

- **WHEN** 使用者檢視 recent runs
- **THEN** 每筆 run 標示 kind，Flow Test 與 Text Test runs 可區分且互不干擾
