# Design: llm-text-test

## Context

Flow Test（`profile-test-runs`，已實作待 archive）建立了 run/event 儲存、sanitizer、`ToolDispatcher`、REST API 與 Profile Editor panel，但 runner 是 deterministic 的，不打 LLM。本 change 在同一套基礎設施上加一個 LLM-backed runner。

Runtime 現況（研究結論，見 `agents/agent.py` / `agents/runtime/providers.py`）：

- Pipeline mode 的 LLM 由 `resolve_session_components()` 建構，但該函式同時建 STT/TTS——text test 不能直接用，需要 LLM-only 的解析路徑（重用 `providers.py` 的 spec → `inference.LLM` / `google.LLM` 邏輯與 `constants.py` 預設值）。
- Prompt instructions 的組裝在 `create_agent_class()`（global prompt + identity + QA + hours preamble）；text test 必須用同一套 helpers，否則測的不是 runtime 真實 prompt。
- Graph runtime 的 handoff 依賴 `AgentSession` 與 Agent instances，無法在無 room 的環境重用；需要獨立的 graph text runner，重用 `runtime/graph.py validate_graph` 與 node instruction 組裝。
- Realtime mode 走 `TextInputRealtimeModel`（Gemini Live），需要 realtime session——text-only 測試不應走這條路。

## Goals / Non-Goals

**Goals:**
- 真實 LLM 文字測試：prompt mode 單/多輪對話、graph mode 由 LLM tool call 決定路由。
- 重用 Flow Test 的儲存、sanitizer、API、panel，以 `kind` 區分。
- 工具維持 dry-run（合成結果餵回 LLM），無外部副作用。
- Mocked-LLM 單元測試覆蓋主要路徑；真實 LLM 整合測試以 env gate。

**Non-Goals:**
- 語音 / LiveKit room / voice Try 替代。
- Live 工具真實執行（intent-only 維持）。
- 自動 graph route coverage、LLM-as-judge 評分。
- Per-node model 切換（沿用 v1 約束：宣告時 log，用 session LLM）。

## Decisions

1. **LLM-only resolver，而非重用 `resolve_session_components()`**
   新增 `resolve_text_test_llm(profile)`：只解析 `models.llm` spec 成 LiveKit LLM instance。替代方案是重構 `resolve_session_components` 拆三段——影響 runtime 熱路徑，風險高於收益，v1 不做。

2. **直接呼叫 `llm.chat(chat_ctx, tools=...)` 而非 `AgentSession`**
   `AgentSession` 綁 room/audio lifecycle。text test 用 LiveKit LLM API 的 chat stream + `collect()`，自行維護 `ChatContext` 與 tool-call loop。這與 runtime 的 LLM 呼叫語意一致（同 provider、同 instructions），差異只在沒有 VAD/STT/TTS 包裝。

3. **Graph text runner：合成 `goto_*` tools 模擬 handoff**
   每個 node 一個 chat 步驟：instructions = global preamble + node prompt（與 `build_graph_root_agent` 同一組裝函式，`_build_node_instructions`）；tools = node domain tools（dry-run dispatcher 包裝）+ 每條 `user_turn` edge 一個 `goto_<target>` 合成 tool（description 帶 NL condition，與 runtime `_make_transition_tool` 的產生方式對齊）。`tool_result` edge 語意：domain tool 的 dry-run 結果先餵回 LLM 讓它完成本輪回覆，回覆完成後無條件轉移到 target node（對齊 runtime v1：LLM 講完結果即 handoff，不由 LLM 決定是否轉移）。LLM 呼叫 `goto_*` → 記 `edge_selected` + `node_entered`，切到 target node 繼續。終止條件：handoff node、end node、或 `max_steps`（預設 10）。

   **ChatContext 生命週期**：全 run 單一 ChatContext，user/assistant/tool 訊息跨輪、跨 node 累積不重置；node 轉移時只替換 system instructions 與 tools（與 runtime handoff 保留對話歷史的語意一致）。轉移事件記錄 node 邊界，不在 context 內插入分隔標記。

4. **多輪 messages 為一等公民**
   Request 帶 `messages: [str]`（Flow Test 的單 `message` 保持相容）。每輪：append user message → chat → 處理 tool calls → 記 `llm_response`。graph mode 下 node state 跨輪保留。

5. **同表加 `kind` 欄位，不開新表**
   `profile_test_runs.kind`（`flow` | `llm_text`，default `flow`，走 `_add_missing_columns` migration）；多輪 messages 存 `user_messages_json`（新欄位），既有 `user_message` 保留存首輪保相容。事件加新 types（`llm_response`、`token_usage`、`edge_selected`），payload `schema_version` 升為 2，前端 parser 依版本容錯（v1 事件照舊顯示）。替代方案是新表——但 list/detail API、panel、sanitizer 全部要複製，不值得。

   **Sanitizer 對 LLM 自然語言的規則分流**：結構化 payload（tool call 參數、config）照既有 key-based 規則；`llm_response` 的回覆全文改用保守的 pattern-based 規則（只紅線明確格式如 `KEY=value` 的 env secret 樣式與 URL query credentials），避免 key-based 遞迴規則誤傷對話中提到「token」等字的正常內容。新增 `sanitize_llm_text(text) -> str`。

6. **Realtime profile fallback**
   `models.mode: realtime` 的 profile：不建 Gemini Live session，改用 pipeline 預設 LLM（`constants.py`）跑 prompt/graph text test，並記 `warning` 事件說明「text test 以 fallback LLM 執行，非 realtime 模型」。替代方案是直接拒絕——但這會讓 realtime profiles 完全無法用 text test，價值損失太大。

7. **逾時與成本控制**
   單輪 LLM 呼叫 timeout（預設 30s，沿用 `TEXT_RUN_TIMEOUT_SECONDS` 模式）；全 run 上限 `max_steps`；事件記 token usage（LLM API 有回 usage 時）。失敗（timeout、API error）→ run `failed` + `error` 事件，不留 running 殭屍（重用 finalize 語意）。

8. **測試策略**
   - 單元：fake LLM（可腳本化回覆序列，含 tool_call 回覆）注入 runner，驗 prompt path、graph user_turn 路由、tool_result 轉移、多輪、realtime fallback、timeout→failed。
   - 整合（gated）：`LLM_TEXT_TEST_INTEGRATION=1` 才跑真實 LLM，CI 預設 skip。

## Risks / Trade-offs

- [Graph text runner 與 runtime 語意漂移] → 兩邊共用 instruction 組裝與 edge→tool 產生函式（抽出共用 helper），並在測試中 assert 產生的 tool schema 一致。
- [LLM 非確定性導致測試結果不穩] → run log 完整記錄 LLM 回覆與 tool calls 供人工判讀；不做自動 pass/fail 斷言（v1）。
- [Token 成本失控] → max_steps + 單輪 timeout + usage 記錄；panel 顯示 usage。
- [Fake LLM 與真實 LiveKit LLM 介面漂移] → fake 實作 LiveKit `llm.LLM` 介面（非自訂 duck type），SDK 升級時型別檢查會抓到。
- [`kind` 欄位 default `flow` 對既有 rows 的語意] → 既有 runs 全是 flow test，default 正確；API list 加 kind filter 時舊資料不受影響。

## Open Questions

- Panel UI 是雙 tab（Flow / Text）還是單 panel + mode 切換？（實作時依現有 panel 結構決定，傾向 tab。）
  - ✅ 已定案：單 panel + kind tab（Flow / LLM Text），多輪輸入為一行一則訊息。
- `google.LLM` direct path 的 credentials 在 API server 環境是否齊備？（integration test gate 可先驗。）
- livekit-agents SDK 的 `llm.chat()` tool-call 回傳結構（FunctionCall 物件形狀、單次多 tool calls、inference.LLM vs google.LLM 語意差異）需在實作前用 spike test 驗證（tasks 2.0）。
  - ✅ Spike 結論（livekit-agents 1.5.2，實測 inference.LLM 無 room 成功）：
    - `llm.chat(chat_ctx=..., tools=[...])` 回傳 `LLMStream`，chunk 為 `ChatChunk(id, delta, usage)`；`delta.tool_calls` 是 `FunctionToolCall(type, name, arguments(JSON str), call_id)` list，單 chunk 可帶多個 tool calls。
    - Tool 結果餵回：`ChatContext` 插入 `FunctionCall(call_id, name, arguments)` + `FunctionCallOutput(call_id, name, output, is_error)` 後再次 `chat()`。
    - usage 出現在最終 chunk 的 `CompletionUsage(prompt_tokens, completion_tokens, total_tokens)`。
    - 無 room/job context 時需 `http_context._new_session_ctx()`（同 `_probe_gateway` 既有模式）。
    - 合成工具用 `function_tool(noop, raw_schema={name, description, parameters})`；runner 自行攔截 stream 的 tool calls，工具函式本體不會被呼叫。
