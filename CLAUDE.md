# voice-agent-workshop

LiveKit-based 語音 Agent 平台。Profile-driven Agent 系統，admin UI 管理 profile / 工具 / 部署 / sessions。

主要架構：
- `agent.py` — LiveKit Agent entrypoint（pipeline + realtime 雙模式）
- `agent_factory.py` — 動態 Agent class 建立（讀 profile YAML/DB）
- `agent_tools.py` — Tool factory registry
- `api/` — FastAPI 管理 API（profiles / sessions / deploy / tools / test）
- `frontend/` — Next.js admin UI + voice 測試頁
- `db/` — SQLAlchemy（SQLite，profile / session / cost 持久化）
- `profiles/` — YAML profile 定義（fallback 來源）

---

## Profile Editor v2（2026-05-14 啟動）

> V1 Admin UI 重新設計已完成，歸檔於 `docs/archive/ADMIN_UI_REDESIGN_V1_2026-05.md`

### 設計方向

參考 Retell AI / Vapi 的 Agent Builder 介面，將現有 Tab-based 編輯器改為 **Split-panel Prompt-first** 架構：
- **中央 60%**：System Prompt 永遠可見（Welcome Message + Instructions），搭配 CodeMirror 6 編輯器
- **右側 40%**：可折疊設定面板（Tools / QA / Hours / Handoff / Identity / Advanced）+ 頂部 Flow minimap
- **Header**：Stack summary chips（Gemini Live · Deepgram · zh）+ Save + Try
- **AI Generate**：右上角按鈕呼叫 Gemini 2.0 Flash Lite 產生 prompt 初稿

### 路徑

Prototype 建在 `/admin/profiles/[id]/v2`，不動現有 v1 頁面。驗證後再替換。

### 進度

| # | 內容 | 狀態 |
|---|------|------|
| 1 | `useProfileForm` hook 抽出 | ✅ |
| 2 | `ProfileEditorLayout` split-panel | ✅ |
| 3 | 右側折疊區塊 6 個元件 | ✅ |
| 4 | 中央 Prompt Editor（CodeMirror 6） | ✅ |
| 5 | Header bar + Stack chips | ✅ |
| 6 | Flow minimap 整合右側面板頂部 | ✅ |
| 7 | AI Generate Prompt（Gemini 2.0 Flash Lite） | ✅ |
| 8 | v2/page.tsx 組裝 + Profiles 列表加 Beta 入口 | ✅ |
| 9 | Docker build 驗證 + 瀏覽器 QA | 🔄 |

### AI Generate Prompt 設計

- 後端 endpoint：`POST /api/admin/generate-prompt`
- 使用 `GOOGLE_API_KEY`（已有），模型 `gemini-2.0-flash-lite`
- 輸入：使用者描述（business type + 功能需求）
- 輸出：完整 system prompt 初稿
- 前端：System Prompt 區域右上角「✨ Generate」按鈕 → modal 輸入描述 → 填回編輯器

---

## 工程慣例

- 安全 / 中間件 / auth：Apr 30 review 後已 hardened，動到 `frontend/middleware.ts`、`frontend/app/api/admin/*`、`api/routes_test.py` 前先看 git log 理解
- Admin 路由結構：`frontend/app/admin/(authenticated)/` route group 包住所有登入後頁面（共用含 sidebar 的 layout），`frontend/app/admin/login/` 維持平行、不套 sidebar。新增登入後頁面請放進 `(authenticated)/` 內
- 登入跳轉用 `window.location.assign()` 而非 `router.replace()`：login 頁與 dashboard 在不同 layout 下，但 App Router 仍會 prefetch dashboard 的 RSC payload；prefetch 發生時還沒 cookie，middleware 回 redirect 並被 client cache，導致登入後 `router.replace` 拿到的是舊的 redirect。hard navigation 直接繞過 client cache
- Test：`uv run pytest tests/ -q`，目前 147 pass。`tests/test_api.py` 的 `client` fixture 會 unset `ADMIN_API_TOKEN`，auth 強制驗證用 `secured_client`
- DB：SQLite，profile 透過 `db.profile_store` 持久化；YAML 是 fallback。`db.engine` 是 module-global singleton，conftest.py 已將測試 DB 指向 `:memory:`
- Profile 改名 / tool 拿掉時記得同步更新 test_agent_system.py 的 assertion
- Cost：realtime 用 Gemini Live token rates（`db/cost.py`），pipeline 走 LLM/STT/TTS 分開計費

### Realtime mode 架構（TextInputRealtimeModel）

Realtime mode **不是**純 Gemini audio-in → audio-out。Gemini Live API 接收原始音頻時，audio token 隨對話時間累積，延遲從 1–2 秒遞增到 20–30 秒（已在所有 observability 資料確認）。

解法：`TextInputRealtimeModel`（`agent.py`）封裝 Gemini Live，攔截 `push_audio`，改由外部 Deepgram STT 轉寫後以文字輸入 Gemini。

實際信號流：
```
語音 → Silero VAD → Deepgram STT → text
     → on_user_turn_completed → session.generate_reply(user_input=text)
     → Gemini Live（文字輸入）→ 語音輸出
```

因此 `AGENT_STT_PROVIDER` 在 realtime 和 pipeline 兩種 mode 下**都有效**：
- `inference`（預設）— 走 LiveKit Inference gateway（Cloud 部署用）
- `deepgram` — 直連 Deepgram API key（Try button 本機測試用，避免吃 free plan STT concurrency quota）

### LiveKit Agents multi-process 陷阱

LiveKit Agents 的 worker 用 multi-process 模型：`entrypoint()` 是在 SDK fork 的 **child process** 執行，不繼承 parent 的 `sys.argv`。

影響：`uv run agent.py connect --profile restaurant` 的 `--profile` flag 只對主 worker process 有效；SDK fork 出來跑 `entrypoint()` 的 child process 找不到 `--profile`，會 fallback 到 `AGENT_PROFILE` env var。

修法（已在 `api/routes_test.py` 實作）：`child_env` 必須同時帶 `AGENT_PROFILE=profile`（env var child process 會繼承）。**不可移除這一行**，否則 Try button 全部 fallback 到預設 profile。

```python
child_env = {**os.environ, "AGENT_STT_PROVIDER": "deepgram", "AGENT_PROFILE": profile}
```

## 部署

- LiveKit Cloud：`lk agent deploy`，`AGENT_PROFILE` env 控制預設 profile
- Docker：`docker compose up -d --build`（frontend port 3004 對外；api 用 `expose: 8083`，僅 compose 內網可達，由 frontend 透過 `http://api:8083` 連）
- Realtime 模式（預設）：Gemini Live + Deepgram STT（避開 audio token 累積延遲 bug，見上方架構說明）

### SIP 接入的 profile 限制

**LiveKit Cloud dashboard 設定的 SIP dispatch rule 沒有 metadata 欄位**，無法動態切換 profile。SIP 來電的 profile 永遠固定在 `AGENT_PROFILE` secret。

若需要不同電話號碼對應不同 profile，只能：
1. 透過 LiveKit API（非 dashboard）建立 dispatch rule，可在 `room_config.agents[].metadata` 帶 `{"profile": "dental_clinic"}`，agent 的 `_get_runtime_profile_name()` 會從 `ctx.job.metadata` 讀取
2. 或部署多個 Cloud agent（不同 `agent_name`），各自對應不同 `AGENT_PROFILE` secret
