# Proposal: llm-text-test

## Why

Flow Test（`profile-test-runs`）是 deterministic smoke：驗證 prompt/graph 接線但不打 LLM，無法驗證真實對話行為——prompt 品質、LLM 是否選對工具、graph 分流是否照預期路由。目前唯一的真實測試是 voice Try（要開 LiveKit room、吃 STT/TTS quota、慢且難重現）。需要一個文字進、文字出、走真實 LLM 的測試通道，作為 voice Try 之前的快速迭代工具。

## What Changes

- 新增 LLM-backed text test runner：對已存 profile 以真實 LLM 執行文字對話測試，與 Flow Test 並存（不取代）。
- **Prompt mode**：以 profile 的 LLM 設定建立 LLM-only client（不建 STT/TTS session），用與 runtime 相同的 instructions 組裝邏輯，跑 `llm.chat()` 收集回覆與 tool calls。
- **Graph mode**：graph text runner——每個 node 用該 node 的 instructions + 合成 `goto_*` transition tools + 真實 domain tool schemas；LLM 的 tool call 決定 edge 轉移；loop 直到 handoff / end node / max steps。
- **多輪腳本**：一次 run 可帶多則 user messages 依序執行（測 `user_turn` edge 需要多輪），事件記錄每輪的 node path。
- **工具執行**：沿用 `ToolDispatcher` dry-run 語意——LLM 收到合成的 planned-call result，不觸發外部副作用。live mode 維持 intent-only。
- **Realtime profiles**：不走 Gemini Live realtime path；fallback 用 pipeline/預設 LLM 執行並記 warning 事件。
- **儲存與 API**：重用 `profile_test_runs` / `profile_test_run_events` 資料表與 event sanitizer；新增 run kind 欄位區分 `flow` / `llm_text`；API 沿用 `/api/profiles/{id}/test-runs` 加 kind 參數。
- **UI**：Profile Editor 測試 panel 區分「Flow Test」（deterministic）與「Text Test」（LLM-backed），Text Test 顯示真實 LLM 回覆、tool calls、graph path、token/latency 資訊。

**明確不做**：
- 不啟 LiveKit room、不碰語音（STT/TTS/voice Try 不變）。
- 不實作 live 工具真實執行（仍是 intent-only，另案處理）。
- 不做自動 graph route coverage 遍歷（另列 TODOS follow-up）。
- 不做 LLM-as-judge 自動評分；v1 由人讀 run log 判斷。

## Capabilities

### New Capabilities

- `profile-llm-text-test`: LLM-backed 文字對話測試——prompt/graph 兩種模式、多輪腳本、tool call 記錄、realtime fallback、run kind 區分與 UI 呈現。

### Modified Capabilities

（無——`profile-test-runs` capability 尚未 archive 進 `openspec/specs/`，其 flow test 行為不變；panel 的呈現調整屬於本 capability 的新需求。）

## Impact

- `agents/runtime/profile_test_runner.py`：擴充或新增 `llm_text` runner（LLM-only resolver、graph text runner、多輪 loop）。
- `agents/runtime/providers.py` / `constants.py`：重用 LLM spec 解析（`inference.LLM` / `google.LLM`）。
- `agents/db/`：`profile_test_runs` 加 `kind` 欄位（migration）；event payload 可能加新 event types（`llm_response`、`token_usage`）→ `schema_version` bump。
- `agents/api/routes_profile_test_runs.py` / `schemas.py`：request/response 擴充 kind 與多輪 messages。
- `frontend/components/admin/profile-text-test-panel.tsx`、`frontend/lib/admin-api.ts`：雙 tab 或 mode switch、新 event 呈現。
- 相依：需要可用的 LLM credentials（LiveKit Inference 或 Google direct）；測試以 mocked LLM 為主，真實 LLM 整合測試 gated。
- 成本：每次 run 產生真實 LLM token 花費；事件記錄 usage 供追蹤。
