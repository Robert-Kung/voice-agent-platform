# Voice Agent Platform

LiveKit-based 語音 Agent 平台。Profile-driven，admin UI 管理多個 agent 設定 / 工具 / 部署 / sessions。

> 詳細架構與資料流：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
> 三層工具設計與重構進度：[`CLAUDE.md`](CLAUDE.md)

---

## 系統概覽

```
┌──────────────┐  REST   ┌──────────────┐
│ Admin UI     │ ──────▶ │ Management   │
│ Next.js :3004│         │ API (FastAPI)│ ──┐
└──────────────┘         │ :8083        │   │  SQLite
                         └──────────────┘   │ data/agent_platform.db
                                            ▼
                          ┌──────────────────────┐
                          │ Agent Worker         │
                          │ agent.py + LiveKit   │
                          └──────────────────────┘
                                  ▲
                                  │ Voice (WebRTC / SIP)
                                  │
                                User
```

**三層工具架構：**
- **Tier 1** — 內建 Python 工具（`get_current_time`，使用者勾選）
- **Tier 2** — Profile 結構化設定渲染進 instructions（QA / Service Hours / Handoff）
- **Tier 3** — Admin UI 直接定義 HTTP webhook 工具（無需寫 Python）

---

## 內建 Profiles

| Profile | 場域 | 重點 |
|---|---|---|
| `car_inspection` | 汽車代檢中心 | 服務項目 + QA + 真人轉接 |
| `dental_clinic` | 幸福牙醫診所 | 預約引導 + 多診療項目 |
| `restaurant` | 好食光餐廳 | 訂位 + 菜單 QA |
| `elevator_repair` | 電梯報修中心 | **Tier 3 POC**：HTTP webhook 開單 |
| `example` | 樣版 | 新場域起手 |

---

## 快速啟動

### Docker Compose（推薦）

```bash
# 一鍵啟動 agent + api + frontend
docker compose up -d --build

# 查看狀態 / log
docker compose ps
docker compose logs -f api

# 訪問
open http://localhost:3004          # 語音測試
open http://localhost:3004/admin    # 管理後台（先 /admin/login）
open http://localhost:8083/docs     # OpenAPI
```

SQLite DB 掛載於 `./data/agent_platform.db`，container 重建不會遺失資料。

若 agent 已在 LiveKit Cloud 上跑：

```bash
docker compose up -d --build api frontend
```

### 本機開發（不用 Docker）

```bash
# Terminal 1: Agent worker
uv run agent.py dev

# Terminal 2: Management API
uv run uvicorn api.main:app --reload --port 8083

# Terminal 3: Frontend
cd frontend && pnpm dev
```

---

## 環境變數

```env
# LiveKit Cloud（必填）
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=

# Realtime mode（預設）
GOOGLE_API_KEY=          # Gemini Live
DEEPGRAM_API_KEY=        # STT（避開 Gemini Live audio token bug）

# Pipeline mode（替代）
OPENAI_API_KEY=

# Admin UI 保護
ADMIN_PASSWORD=          # 未設則本機開發跳過 auth

# DB
AGENT_DB_PATH=data/agent_platform.db
# 或 AGENT_DB_URL=postgres://...（Cloud 共用 sessions 時用）

# Tier 3 HTTP tool secrets（依 profile）
ELEVATOR_API_KEY=        # elevator_repair profile 需要
```

可用 LiveKit CLI 自動填：

```bash
lk cloud auth
lk app env -w -d .env
```

---

## 主要功能

### Profile 管理（`/admin/profiles`）
結構化編輯：Identity / Messages / **Handoff to Human** / **QA Database**（inline ↔ tool 切換）/ **Service Hours** / Built-in Tools / **Custom HTTP Tools**。Advanced JSON 給未涵蓋欄位。

### Sessions（`/admin/sessions`）
分頁列表（10/25/50）+ Profile / Status / Mode filter。Detail 頁有 Conversation chat（function call 折疊）、Metrics 表、Raw events tabs、LiveKit Cloud 錄音連結。

### Deploy（`/admin/deploy`）
LiveKit Cloud agent 狀態 / 切 active profile / Secrets 列表 / 帶 level 著色的 deploy/build logs。

### Tools（`/admin/tools`）
列出當前可用工具（Tier 1 內建 + 各 profile 自定 Tier 3）。Tier 3 工具直接在 profile 編輯頁新增。

---

## 部署到 LiveKit Cloud

```bash
lk agent deploy
lk agent secrets set AGENT_PROFILE=car_inspection
# 若 profile 用了 Tier 3 HTTP tool：
lk agent secrets set ELEVATOR_API_KEY=...
```

Cloud 與本機共用 sessions：設定 `AGENT_DB_URL`（如共享 Postgres），會優先於 `AGENT_DB_PATH`。

### 自訂 API URL（前端）
`NEXT_PUBLIC_ADMIN_API_URL` 是 build-time 編譯進 client bundle，預設 `http://localhost:8080`。非本機部署時：

```bash
# docker-compose.yml
args:
  NEXT_PUBLIC_ADMIN_API_URL: https://api.example.com
```

---

## 安全性

- Admin UI 走 `ADMIN_PASSWORD` cookie session（未設則本機開發跳過）
- Tier 3 HTTP tool 內建 SSRF 防護：擋非 http(s) scheme、`localhost`、RFC1918 私網、link-local、雲端 metadata endpoint
- Secret 走 `${ENV_NAME}` 替換（YAML / DB 不存明碼）

生產環境建議再加：reverse proxy + TLS、IP 白名單或 Cloudflare Access / Tailscale 類 zero-trust 閘道。CORS 預設 `allow_origins=["*"]`，不建議直接面向公網。

---

## 測試

```bash
uv run pytest tests/ -q
# 預期：147 passed
```

主要 test 檔：

| 檔案 | 範圍 |
|---|---|
| `test_db.py` | profile_store / session_store / YAML import idempotency |
| `test_api.py` | FastAPI routes + admin auth |
| `test_cost.py` | Pipeline + Gemini Live 成本計算 |
| `test_http_tool.py` | Tier 3 factory + SSRF 防護（43 tests） |
| `test_agent_system.py` | profile loading / tool mounting / qa modes / human operator |

---

## API 快速參考

| 路徑 | 用途 |
|---|---|
| `GET /health` | 健康檢查 |
| `POST /api/admin/login` / `logout` | ADMIN_PASSWORD cookie |
| `GET / POST /api/profiles` | 列出 / 建立 profile |
| `PATCH / DELETE /api/profiles/{id}` | 更新 / soft-delete |
| `GET /api/sessions?status=&profile_id=&limit=&offset=` | 分頁 sessions（`X-Total-Count` header） |
| `GET /api/sessions/{id}` / `/events` / `/livekit-link` | session 詳情 |
| `GET /api/stats/profiles` / `/daily` | 統計 |
| `GET /api/deploy/status` / `logs` | LiveKit Cloud 狀態 |
| `POST /api/deploy/deploy` / `switch-profile` | 觸發部署 / 切 profile |
| `POST /api/test/start` / `DELETE /api/test/stop/{room}` | 本機 connect-mode（admin Try 按鈕） |
| `GET /api/tools` | 可用工具名稱列表 |

完整 spec：http://localhost:8083/docs

---

## 文件導覽

- [`CLAUDE.md`](CLAUDE.md) — Claude / 維護者用：架構決策 + 重構進度 + 工程慣例
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 系統圖 / profile 渲染管線 / Tool 三層 / Session 生命週期
- [`docs/archive/`](docs/archive/) — 歷史 review 與 MVP plan（保留軌跡，不再維護）
- [`profiles/README.md`](profiles/README.md) — profile YAML 寫法
