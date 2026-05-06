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

## Tool 架構決策（2026-05-04 確立）

工具分三層，**Tier 1 不再增加新工具**，所有新業務需求走 Tier 3。

### Tier 1：內建原語（Python code，使用者可選掛）
最小集，只放每個 agent 都可能需要的通用功能。每個都是「使用者在 admin UI 勾選是否啟用」。

- `get_current_time` — 取得目前時間 + 星期（讓 LLM 配合 system prompt 自行判斷營業狀態）
- （`transfer_to_human` 不算在這層 — 見下方 human_operator 設計）

### Tier 2：Profile 結構化設定 → 渲染進 instructions（不是 tool）
這些「看起來像工具的東西」其實是資料，直接嵌入 system instructions 比 tool call 快、零延遲、無 round-trip。Admin UI 提供結構化表單，render 階段把資料拼進 instructions 字串。

- **QA Database** — 過去的 `lookup_qa` tool。提供兩種模式：
  - `inline` — 啟動時 render 進 instructions（推薦，零延遲）
  - `tool` — 保留 tool call 形式（QA 量大、context 塞不下時用）
  - Admin UI 可在 profile 編輯頁切換
- **Service Hours** — 過去的 `check_business_status` tool。改成把營業時間直接寫進 instructions，搭配 `get_current_time` 工具讓 LLM 自行判斷
- **Human Operator (Handoff)** — 過去的 `transfer_to_human` tool。Profile 設定區塊：
  - `enabled` — 是否啟用真人轉接
  - `greeting` / `instructions` / `voice` / `transfer_message`
  - 實作仍由 `transfer_to_human` factory 掛上，但 UI 不以 tool 呈現

### Tier 3：使用者自定義 HTTP 工具（無需寫 Python）
Admin UI 直接新增「呼叫某個 API endpoint」的工具。一支通用 `make_http_tool` factory，從 profile config 動態建立 `@function_tool`。

YAML schema：
```yaml
tools:
  - name: report_elevator_failure
    description: 當住戶回報電梯故障時呼叫
    endpoint: https://your-api.com/elevator/report
    method: POST
    auth_header: "Bearer ${ELEVATOR_API_KEY}"   # ${ENV_NAME} 替換
    parameters:
      - { name: building, type: string, required: true, description: 棟別 }
      - { name: symptom, type: string, description: 故障狀況 }
```

業務邏輯（送 LINE / 開單 / 寫 DB）住在使用者自寫的 API server，agent 平台只負責對話 + 呼叫。

---

## 重構計畫進度

> 圖例：✅ 已 land / 🟡 進行中（卡在外部依賴）/ ⬜ 未開工

### ✅ 階段 1：工具清理（完成 2026-05-04）
1. ✅ 1.1 刪 `get_current_datetime`（與 `get_current_time` 重複）— 全 profile 改用後者
2. ✅ 1.2 刪 `example.yaml` 引用的不存在 tool `replay_last_prompt`
3. ✅ 1.3 刪 `check_weather`（假資料工具，需要時走 Tier 3 接真 API）
4. ✅ 1.4 刪 `book_appointment` / `search_menu` / `calculate_price`（mock 示範，無真後端）
5. ✅ 1.5 `qa_mode: inline | tool` 切換實作於 `agent_factory.py`（preset `inline`，render 時拼進 instructions）
6. ✅ 1.6 `check_business_status` 移除，services 資料於 render 階段拼進 instructions
7. ✅ 1.7 `human_operator:` namespace 區塊收斂（`agent_tools.py` 含 legacy fallback）

清理後 tool registry 只剩：`get_current_time`、`lookup_qa`、`transfer_to_human`（後兩者依設定條件性掛載）。

### ✅ 階段 2：HTTP Tool（電梯 POC，完成 2026-05-05）
1. ✅ 2.1 `agent_tools.py` 新增 `make_http_tool` factory（讀 endpoint/method/auth/params）
2. ✅ 2.2 YAML schema 擴充：tools 區塊支援 endpoint / parameters 宣告
3. ✅ 2.3 Secret 管理：`${ENV_NAME}` 替換 + URL 白名單（SSRF 擋 localhost、RFC1918、link-local、metadata；43 個專屬測試）
4. ✅ 2.4 Admin UI tools 區塊可動態新增/編輯（Built-in vs Custom HTTP 雙列表）
5. 🟡 2.5 業主側：寫電梯報修 API endpoint（送 LINE push）— **卡業主端**
6. 🟡 2.6 Admin UI 建立 elevator_repair profile + 三端測試（Console / WebRTC / SIP）— **卡 2.5**

> elevator_repair YAML 已建立（`profiles/elevator_repair.yaml`），endpoint 為 placeholder `https://CHANGE_ME.example.com/elevator/report`，部署前需設 `ELEVATOR_API_KEY` env。

### ✅ 階段 3：Admin UI 結構化設定（完成 2026-05-05）
1. ✅ 3.1 Profile 編輯頁 **Handoff to Human** 區塊（取代 transfer_to_human checkbox）
2. ✅ 3.2 **QA Database** 區塊：CRUD QA 條目 + `qa_mode` 切換 inline/tool
3. ✅ 3.3 **Service Hours** 區塊：結構化每服務編輯（多時段 dict 仍走 Advanced JSON）
4. ✅ 3.4 Tools 區塊拆 Built-in / Custom HTTP 雙區塊

### ⬜ 後續可選
- Service Hours 多時段 dict（`hours_text` / `schedule`）的結構化編輯器
- Tier 3 webhook tool 之外的觸發機制（schedule、event）— 視業主需求

---

## 工程慣例

- 安全 / 中間件 / auth：Apr 30 review 後已 hardened，動到 `frontend/middleware.ts`、`frontend/app/api/admin/*`、`api/routes_test.py` 前先看 git log 理解
- Test：`uv run pytest tests/ -q`，目前 147 pass。`tests/test_api.py` 的 `client` fixture 會 unset `ADMIN_API_TOKEN`，auth 強制驗證用 `secured_client`
- DB：SQLite，profile 透過 `db.profile_store` 持久化；YAML 是 fallback。`db.engine` 是 module-global singleton，conftest.py 已將測試 DB 指向 `:memory:`
- Profile 改名 / tool 拿掉時記得同步更新 test_agent_system.py 的 assertion
- Cost：realtime 用 Gemini Live token rates（`db/cost.py`），pipeline 走 LLM/STT/TTS 分開計費

## 部署

- LiveKit Cloud：`lk agent deploy`，`AGENT_PROFILE` env 控制預設 profile
- Docker：`docker compose up -d --build`（frontend port 3004、api port 8083）
- Realtime 模式（預設）：Gemini Live + Deepgram STT（避開 audio token 累積延遲 bug）
