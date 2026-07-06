# Proposal: http-tool-quick-ack

## Why

Live 語音 e2e 驗證發現：HTTP tool（Tier 3 generic）呼叫的外部建單 endpoint side effect 已成功（LINE 單據已送達），但 response 超過 10s timeout，agent 收到 `{"success": false, "error": "請求逾時"}` 後會對使用者宣稱建單失敗——最差情境下誘發使用者重複提交、產生重複單據。外部 endpoint 由 admin 自行設定、不受平台控制，無法要求對方實作 202 quick-ack contract，因此必須在 agent 端解決。

## What Changes

- HTTP tool config 新增 `response_mode` 欄位：`wait`（預設，現行為）或 `quick_ack`。
- `quick_ack` 模式：請求以背景 task 發送，工具立即回傳 accepted ack（`{"success": true, "accepted": true, "detail": ...}`），LLM 據此告知使用者「請求已送出」；背景 task 完成後記 log（成功 info / 失敗 warning），不回饋對話。
- `wait` 模式 timeout 語意修正：timeout 回傳從單純 `success: false` 改為帶 `pending: true` 與明確 detail（請求已送出、後端可能仍在處理、請勿重複提交），讓 LLM 不會斷言失敗。
- 非 timeout 的錯誤（連線失敗、4xx/5xx）維持現行 `success: false` 語意不變。
- Admin UI HTTP tool 卡片新增 response mode 控制。
- config 驗證：`response_mode` 僅接受 `wait` / `quick_ack`，非法值 raise `ValueError`（與現有 config 驗證一致）。

## Capabilities

### New Capabilities

- `http-tool-invocation`: Tier 3 generic HTTP tool 的呼叫語意——response mode（wait / quick_ack）、timeout 的 pending 語意、錯誤回傳 contract。

### Modified Capabilities

（無——`openspec/specs/` 現有 capability 均不涵蓋 HTTP tool 呼叫語意）

## Impact

- `agents/agent_tools.py` — `make_http_tool`：config 解析 + `_handler` 分流（quick_ack 背景 task / wait timeout 回傳格式）。
- `agents/tests/test_http_tool.py` — 新增 response_mode 驗證與行為測試。
- `frontend/hooks/use-profile-form.ts` — HTTP tool 型別加 `response_mode`。
- `frontend/components/admin/profile-sections/tools-section.tsx` — HttpToolCard 加 response mode select。
- `docs/ARCHITECTURE.md` — HTTP tool YAML 範例補 `response_mode`。
- 不影響 Flow Test（dry-run 不執行 HTTP）、graph runtime（tool wrapper 透明包裝回傳值）、cost 計算。
