# Design: http-tool-quick-ack

## Context

`make_http_tool`（`agents/agent_tools.py`）是 Tier 3 generic HTTP tool factory：admin 在 UI 設定 endpoint / method / auth / parameters，runtime 動態生成 LiveKit function tool。現行 `_handler` 使用 `aiohttp.ClientSession(timeout=ClientTimeout(total=timeout))` 同步等待回應，timeout（預設 10s，上限 60s）觸發時回傳 `{"success": false, "error": "請求逾時（Ns）"}`。

Live e2e 觀察到的失效模式：外部建單 endpoint 的 side effect 已成功（LINE 單據送達），但 HTTP response 慢於 timeout。LLM 收到 `success: false` 後告訴使用者「建單失敗」，語意錯誤且誘發重複提交。

限制條件：
- 外部 endpoint 由 admin 設定、不受平台控制，不能假設對方提供 202 quick-ack 或 job polling API。
- 語音情境下拉長 timeout = dead air，60s 上限內乾等不是解。
- graph runtime 的 `tool_result` edge wrapper（`functools.wraps` 包裝 domain tool）對回傳值透明，不需改動。
- Flow Test dry-run 不執行真實 HTTP（`profile_test_runner.py` 直接回 stub），不受影響。

## Goals / Non-Goals

**Goals:**
- 提供 `quick_ack` response mode：fire-and-forget + 立即 ack，消除語音 dead air 與假失敗。
- 修正 `wait` mode 的 timeout 語意：明確告知 LLM「結果未知、可能已成功、勿重複提交」。
- config 驗證與現行風格一致（非法值 raise `ValueError`，由 `build_tools_for_agent` skip + log）。

**Non-Goals:**
- 不做 async job polling / callback contract（外部 endpoint 無此能力）。
- 不做背景結果回饋對話（LiveKit session 注入 mid-turn message 屬另一個 change 的範圍）。
- 不改非 timeout 錯誤（4xx/5xx、連線失敗）的語意。
- 不動 Flow Test / LLM Text Test 的 dry-run 行為。

## Decisions

### D1: agent 端 response mode，而非外部 contract 要求

**選擇**：在 tool config 加 `response_mode: wait | quick_ack`，預設 `wait`。
**替代**：要求外部 endpoint 實作 202 quick-ack —— 否決，Tier 3 工具的價值就是「不需外部配合、admin 自行接任意 API」。

### D2: quick_ack 用 `asyncio.create_task` + module-level task registry

**選擇**：`_handler` 在 quick_ack 模式下把實際 HTTP 呼叫包成 coroutine 丟 `asyncio.create_task`，把 task 存入 module-level `set`（done callback 移除）避免被 GC 提前回收；立即回傳 `{"success": true, "accepted": true, "detail": "<請求已送出訊息>"}`。背景 task 完成時記 log：成功 `logger.info`、失敗 `logger.warning`（含 status/error）。
**替代**：
- 等待第一個 byte / header 才 ack —— 複雜度高且多數慢 endpoint 是整體處理慢，收益有限。
- 短 timeout + 立即降級 —— 仍有 dead air，且語意混亂。

背景 task 的 timeout 沿用 config `timeout_seconds` 不變（防 task 洩漏無限掛著）。

### D3: wait mode timeout 回傳 `pending: true`

**選擇**：timeout 時回傳
```json
{"success": false, "pending": true, "error": "timeout",
 "detail": "請求已送出但未在時限內收到回應；後端可能仍在處理，請告知使用者稍候確認，不要重複提交"}
```
`success: false` 保留（結果確實未確認），新增 `pending: true` + detail 指示 LLM 的敘事方向。
**替代**：`success: true` + accepted —— 否決，wait mode 下 timeout 不等於成功，誤報成功比誤報失敗更糟（使用者以為完成而離開）。

### D4: UI 用 select 而非 checkbox

HttpToolCard 加一個雙選項 select（等待回應 / 立即回覆），與現有 method select 風格一致；`use-profile-form.ts` 的 http tool 型別加可選 `response_mode` 欄位，未設定即後端預設 `wait`。

## Risks / Trade-offs

- [quick_ack 下真實失敗不可見於對話] → 背景 log 記 warning，session log / observability 可查；proposal 明確定位為適用「必達型通知類」API（如建單），admin 自行判斷。
- [背景 task 在 agent process 關閉時被取消] → 語音 session 結束到 process 關閉有 drain 期；殘餘風險屬邊緣情境，log 可辨識（task cancelled warning）。
- [LLM 忽略 pending detail 仍說失敗] → detail 文字明確指示敘事；LLM Text Test 可驗證 prompt 對 pending 結果的處理。

## Migration Plan

純新增欄位，預設值 = 現行為，無 migration。既有 profile YAML / DB 不需變更。Rollback = revert commit。

## Open Questions

（無——scope 已收斂）
