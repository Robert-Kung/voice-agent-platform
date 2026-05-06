# Agent Management Platform — 實施計畫（MVP）

本計畫描述在現有 `first-livekit` 專案上，擴充為一個「多 Agent / 多使用者」管理平台的最小可行版本。
基於使用者決策：**不預錄音檔、只用 session_report 做分析、不做認證、用 metrics 推導成本**。

---

## 1. 範圍與取捨

| 項目 | 決策 | 備註 |
|---|---|---|
| Profile 管理 | ✅ DB 驅動（取代 YAML） | 由 UI 編輯 |
| Session 紀錄 | ✅ 完整 transcript + metrics | 依賴既有 `session_report` |
| 錄音 (Egress) | ❌ **不啟用** | 問題 session 再到 LiveKit Cloud dashboard 查 |
| Analytics REST 同步 | ❌ **不啟用** | 只用 session_report 推導；免費版相容 |
| 成本估算 | ✅ 用 `metrics_collected` 的 token / TTS / STT 時長推導 | 費率表寫死在 code |
| 認證 / 多租戶 | ❌ MVP 不做 | 僅內網使用 |
| 即時監控 | ✅ 以 DB polling 呈現「進行中 session」 | 不做 WebSocket |

---

## 2. 架構總覽

```
┌───────────────────────────┐
│  Frontend (Next.js App)   │  <- 已存在；擴充 admin 頁面
└──────────────┬────────────┘
               │ REST
┌──────────────▼────────────┐
│  Management API           │  <- 新增：FastAPI
│  - /profiles              │
│  - /sessions              │
│  - /stats                 │
└──────────────┬────────────┘
               │
        ┌──────▼──────┐
        │   SQLite    │  <- 新增：單檔 DB（後續可換 Postgres）
        └──────┬──────┘
               │
┌──────────────▼────────────┐
│  Agent Worker (agent.py)  │  <- 改動：從 DB 讀 profile、寫入 session
└───────────────────────────┘
```

---

## 3. 資料模型（SQLite / SQLAlchemy）

### 3.1 `profiles`
| 欄位 | 型別 | 說明 |
|---|---|---|
| id | UUID | PK |
| name | TEXT UNIQUE | 對應 LiveKit room / dispatch 名稱 |
| display_name | TEXT | UI 顯示用 |
| description | TEXT | |
| config_json | TEXT (JSON) | 對應目前 YAML 內容（llm、tts、stt、instructions、tools…） |
| is_active | BOOL | 停用後 worker 拒絕 dispatch |
| created_at / updated_at | TIMESTAMP | |

> 相容層：啟動時若 `profiles` 空表，自動從 `profiles/*.yaml` 匯入一次。

### 3.2 `sessions`
| 欄位 | 說明 |
|---|---|
| id (UUID) | PK |
| room_name | LiveKit room name |
| profile_id | FK -> profiles |
| participant_identity | |
| started_at / ended_at | |
| status | running / completed / failed |
| shutdown_reason | 來自 `session_report.shutdown_reason` |
| duration_seconds | |
| total_cost_usd | 由 metrics 推導 |
| raw_report_json | 整包 session_report dump |

### 3.3 `session_events`
| 欄位 | 說明 |
|---|---|
| session_id | FK |
| seq | 單調遞增 |
| event_type | user_message / agent_message / tool_call / metric / error |
| timestamp | |
| payload_json | 明細 |

> 來源：直接從 `session.history.items` 與 `metrics_collected` event 寫入。

### 3.4 `daily_stats`（物化視圖，每日 rebuild）
| 欄位 |
|---|
| date, profile_id, session_count, total_duration_sec, total_cost_usd, avg_duration_sec |

---

## 4. 程式碼改動

### 4.1 新增檔案
```
db/
  __init__.py
  models.py          # SQLAlchemy models
  session_store.py   # sessions / events 寫入邏輯
  profile_store.py   # profiles CRUD
  migrate.py         # 建表 + YAML 匯入
api/
  __init__.py
  main.py            # FastAPI app
  routes_profiles.py
  routes_sessions.py
  routes_stats.py
  cost.py            # metrics -> USD
frontend/app/admin/
  profiles/page.tsx
  profiles/[id]/page.tsx
  sessions/page.tsx
  sessions/[id]/page.tsx
  dashboard/page.tsx
```

### 4.2 改動檔案
- `agent_factory.py`：新增 `load_profile_from_db(name)`，沿用既有 `build_agent_session()` 簽章。
- `agent.py`：
  - `entrypoint` 開始：在 DB 建立 `sessions` row（status=running）。
  - 既有 `session_report` callback：更新 `sessions`、批次寫入 `session_events`、呼叫 `cost.compute(report)` 寫入 `total_cost_usd`。
  - 既有 transcript 檔案輸出保留（debug 用），但 DB 才是正式來源。
- `docker-compose.yml`：加入 `api` service（port 8080）、共用 volume 放 SQLite 檔。

### 4.3 不改動
- LiveKit room / dispatch 機制
- `agent_tools.py`
- 前端 voice UI 主流程

---

## 5. API 介面（FastAPI）

```
GET    /api/profiles
POST   /api/profiles
GET    /api/profiles/{id}
PATCH  /api/profiles/{id}
DELETE /api/profiles/{id}   # soft delete (is_active=false)

GET    /api/sessions?profile=&from=&to=&status=&limit=&cursor=
GET    /api/sessions/{id}             # header + 費用 + metrics 摘要
GET    /api/sessions/{id}/events      # 逐筆 transcript / metric / tool_call
GET    /api/sessions/{id}/livekit-link # 產生到 LK Cloud 該 room 錄音頁的連結

GET    /api/stats/daily?from=&to=&profile=
GET    /api/stats/profiles           # 各 profile 累計數
```

> `livekit-link` 回傳 `{url, room_name}`；UI 顯示「去 LiveKit Cloud 查錄音」按鈕，避開 Egress 需求。

---

## 6. 成本推導（`api/cost.py`）

以 `session_report.metrics` 為輸入：

```python
RATES = {
  # USD per 1M tokens
  "llm": {"openai/gpt-4o-mini": {"in": 0.15, "out": 0.60}, ...},
  # USD per minute
  "tts": {"openai": 0.015, "cartesia": 0.02, ...},
  # USD per minute
  "stt": {"deepgram": 0.0043, ...},
}
```

回傳 `{llm_usd, tts_usd, stt_usd, total_usd, breakdown}`；費率未知時記為 `null` 並標記 `incomplete=true`。

---

## 7. 前端頁面

| 路徑 | 內容 |
|---|---|
| `/admin/dashboard` | 今日 session 數、活躍 session、每日成本折線 |
| `/admin/profiles` | 列表 + 新增 / 複製 / 停用 |
| `/admin/profiles/[id]` | JSON 編輯器（monaco）+ 語音試玩按鈕（直接 dispatch 到 LK room） |
| `/admin/sessions` | 表格；篩選 profile / 時間 / status |
| `/admin/sessions/[id]` | 時間軸：user / agent 泡泡 + tool_call 展開 + metrics panel + 「去 LK Cloud 抓錄音」按鈕 |

---

## 8. 實作階段

### Phase 1 — DB 層（0.5 天）
- 建 models、migrate、YAML → DB 匯入腳本
- 單元測試：`profile_store`, `session_store`

### Phase 2 — Agent 整合（0.5 天）
- `agent.py` 改 DB profile loader
- session_report → DB 寫入 + cost 計算
- 本地手動跑一場 voice session，驗證 DB 有完整 transcript + cost

### Phase 3 — Management API（0.5 天）
- FastAPI routes 全數上
- OpenAPI 可瀏覽（/docs）

### Phase 4 — Admin UI（1 天）
- Profiles CRUD
- Sessions 列表 + 詳情
- Dashboard 簡版

### Phase 5 — 部署（0.5 天）
- `docker-compose.yml` 加 api service、SQLite volume
- README 更新啟動指令

**總計約 3 天工時**，不含 UI 打磨。

---

## 9. 後續可延伸（非 MVP）
- 換 Postgres + Alembic migrations
- 接 LiveKit Egress（選擇性 per-session 錄音開關）
- 接 LiveKit Analytics REST（Pro 方案後）
- 多租戶 + OIDC 登入
- Session 全文搜尋（SQLite FTS5 足夠）

---

## 10. 風險與備註
- SQLite 在單機 agent worker OK；若未來多 worker 並發寫入 session_events，需換 Postgres。
- 成本費率寫死 → 每次模型價格變動要改 code；可接受（MVP）。
- 不錄音 → 糾紛 / debug 時需即時去 LK Cloud 抓，流程需在 runbook 中明記。
