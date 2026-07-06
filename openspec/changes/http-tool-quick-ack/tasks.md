# Tasks: http-tool-quick-ack

## 1. Backend — response_mode 解析與 quick_ack handler

- [x] 1.1 `make_http_tool` 解析 `response_mode`（預設 `wait`；非 `wait`/`quick_ack` raise `ValueError`）
- [x] 1.2 抽出單次請求 coroutine（現有 session/request/parse 邏輯），供 wait 與 quick_ack 共用
- [x] 1.3 quick_ack 分支：`asyncio.create_task` + module-level task set（done callback 移除引用），立即回傳 `{"success": true, "accepted": true, "detail": ...}`
- [x] 1.4 背景 task 結果 log：2xx → info；>=400 / timeout / ClientError / cancelled → warning，不外洩例外
- [x] 1.5 wait 分支 timeout 回傳改為 `{"success": false, "pending": true, "error": "timeout", "detail": ...}`；4xx/5xx 與連線錯誤維持原 shape

## 2. Backend — 測試

- [x] 2.1 `test_http_tool.py`：response_mode 驗證（預設 wait、非法值 rejected、合法值 accepted）
- [x] 2.2 quick_ack 行為：慢 endpoint 下 handler 立即回 ack（mock aiohttp）；背景成功 info log、背景失敗 warning log
- [x] 2.3 wait timeout 回傳含 `pending: true` 與 detail；HTTP 500 / 連線錯誤無 `pending`
- [x] 2.4 `cd agents && uv run pytest tests/ -q` 全綠

## 3. Frontend — UI 與型別

- [x] 3.1 `use-profile-form.ts` HTTP tool 型別加 `response_mode?: 'wait' | 'quick_ack'`
- [x] 3.2 `tools-section.tsx` HttpToolCard 加 response mode select（等待回應 / 立即回覆），未設定顯示 wait
- [x] 3.3 `cd frontend && pnpm test` 全綠

## 4. Docs

- [x] 4.1 `docs/ARCHITECTURE.md` HTTP tool YAML 範例補 `response_mode` 與語意說明
- [x] 4.2 `TODOS.md` live e2e follow-up 更新為已處理
