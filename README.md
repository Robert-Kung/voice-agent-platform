# LiveKit Voice Agent Workshop

Welcome to the Voice Agent Workshop! In this workshop, you will learn how to build and test a production-ready voice agent using [LiveKit](https://livekit.io) and [Coval](https://coval.dev).

## Prerequisites

To run this agent, you need the following

- A [LiveKit Cloud](https://cloud.livekit.io) account, project, and API keys
- A Python environment with [uv](https://docs.astral.sh/uv/) installed
- An [OpenAI](https://platform.openai.com) account and API Key
- A [Deepgram](https://www.deepgram.com) account and API Key

## Setup

Step 1: Copy this repository (Click the green "Use this template" button on GitHub)
Step 2: Clone your new copy to your local machine
Step 3: Install dependencies using uv

    ```shell
    uv sync
    ```

Step 4: Create a `.env` file in the root of the project and add your API keys

    ```
    LIVEKIT_URL=
    LIVEKIT_API_KEY=
    LIVEKIT_API_SECRET=
    OPENAI_API_KEY=
    DEEPGRAM_API_KEY=
    ```

You can load the LiveKit environment automatically using the [LiveKit CLI](https://docs.livekit.io/home/cli/cli-setup):

```bash
lk cloud auth
lk app env -w -d .env
```

Step 5: Run your new agent in the console

    ```shell
    uv run agent.py console
    ```

## Web frontend

This agent is compatible with the [LiveKit Agents Playground](https://agents-playground.livekit.io).

To run the agent for the playground, use the `dev` subcomand:

    ```shell
    uv run agent.py dev
    ```

## Development instructions

In this workshop, you will be adding features and functionality to the `agent.py` file. You are free to use the playground or the console mode to speak with your agent as you work on it.

## Testing with Coval

For the Coval sections of the workshop, you need to run your agent in `dev` mode to make it available to Coval.

    ```shell
    uv run agent.py dev
    ```

To setup the Coval connection, follow these steps:

1. Enable the token server from your project's **Options** on the [Settings](https://cloud.livekit.io/projects/p_/settings/project) page in LiveKit Cloud.
2. Copy the `sandboxId` & `sandboxUrl` displayed below the toggle.
3. Sign in to your [Coval](https://www.coval.dev/) account (you should have an email invite already)
4. Click the "Agents" menu item in the top left
5. Click the "Connect Agent" button in the top right
6. Enter a name for your agent
7. Select "LiveKit" as the simulator type
8. For token endpoint, use `https://cloud-api.livekit.io/api/sandbox/connection-details`
9. For the token sandbox id, use the `sandboxId`
10. Add your LiveKit server URL (it's in your `.env` file)
11. Set content type to `application/json`

You should now be ready to test your agent in Coval.

## Post-workshop

You are welcome to continue working on your agent after the workshop, or start a new one. Here are some useful documentation links for content not covered in the workshop:

- [Deploying to production](https://docs.livekit.io/agents/ops/deployment/)
- [Web & mobile starter apps](https://docs.livekit.io/agents/start/frontend/#starter-apps)
- [Telephony integrations](https://docs.livekit.io/agents/start/telephony/)

---

## Agent Management Platform (MVP)

除了 workshop 的單一 agent，本 repo 擴充為「多 Profile / 多 Session」管理平台，包含：

- **Profile CRUD** — 從 DB 管理 agent 配置（取代 YAML）
- **Session 追蹤** — 每場通話自動寫入 DB，含 metrics、成本估算
- **Dashboard UI** — `/admin/*` 提供 profiles / sessions / stats 管理介面
- **Management API** — FastAPI + SQLite，供 UI 與未來整合

詳細設計見 [`AGENT_PLATFORM_PLAN.md`](./AGENT_PLATFORM_PLAN.md)，最近一次品質審查見 [`CODE_REVIEW.md`](./CODE_REVIEW.md)。

### 架構

```
┌───────────────────┐   ┌──────────────────┐   ┌───────────────┐
│ Next.js Frontend  │──▶│ Management API   │──▶│  SQLite       │
│ :3004 (/admin/*)  │   │ FastAPI :8083    │   │  data/*.db    │
└───────────────────┘   └──────────────────┘   └───────┬───────┘
                                                       │
                                ┌──────────────────────▼───────┐
                                │ Agent Worker (agent.py)      │
                                │ 讀 profile / 寫 session      │
                                └──────────────────────────────┘
```

### 使用 Docker Compose（推薦）

一鍵啟動三個 service（agent + api + frontend）：

```bash
# 第一次啟動（會自動跑 DB migration + 從 profiles/*.yaml 匯入）
docker compose up -d --build

# 檢查狀態
docker compose ps
docker compose logs -f api

# 訪問
open http://localhost:3004          # 語音測試頁
open http://localhost:3004/admin    # 管理後台（先 /admin/login，密碼 = ADMIN_PASSWORD env）
open http://localhost:8083/docs     # OpenAPI 文件
```

SQLite DB 掛載於 host 的 `./data/agent_platform.db`，container 重建不會遺失資料。

**若 agent 已部署到 LiveKit Cloud**，可只啟動 api + frontend：

```bash
docker compose up -d --build api frontend
```

### 本機開發（不用 Docker）

需要三個 terminal：

```bash
# Terminal 1: Agent worker
uv run agent.py dev

# Terminal 2: Management API
uv run uvicorn api.main:app --reload --port 8083

# Terminal 3: Frontend
cd frontend && pnpm dev
```

訪問：

- 語音測試：http://localhost:3000
- Admin UI：http://localhost:3000/admin
- API docs：http://localhost:8083/docs

### DB 初始化

API / agent 首次啟動時會自動：

1. 建立 `data/agent_platform.db`
2. 若 `profiles` table 為空，從 `profiles/*.yaml` 匯入為 DB profile

### Cloud 與本機共用 Sessions（重要）

預設使用本機 SQLite（`AGENT_DB_PATH`），因此：

- 本機 `api` 看到的是本機 `./data/agent_platform.db`
- 若 agent 部署在 LiveKit Cloud，Cloud 端不會自動寫回你本機 SQLite

若要讓 Cloud agent 與本機 API 共用同一份 sessions，請設定：

```bash
AGENT_DB_URL=<shared database url>
```

例如共享 Postgres。`AGENT_DB_URL` 會優先於 `AGENT_DB_PATH`。

### LiveKit 測試環境建議

依 LiveKit 文件（Self-hosted deployments）建議，development / staging / production 應使用不同 LiveKit project，避免本機測試 worker 意外接到正式流量。實務上：

- 要測試 Cloud deploy 的 `Try` 流程：使用專用 Cloud project（不要讓本機 worker 連到同一 project）
- 要測本機 agent：使用另一個 dev project（或本機 server）

也可手動跑：

```bash
uv run python -m db.migrate
```

### 自訂 API URL（非本機部署）

前端的 `NEXT_PUBLIC_ADMIN_API_URL` 在 build time 被編譯進 client bundle，預設 `http://localhost:8080`。
若要部署到非本機環境，請在 build 時指定：

```bash
# docker-compose.yml
args:
  NEXT_PUBLIC_ADMIN_API_URL: https://api.example.com

# 或
docker build --build-arg NEXT_PUBLIC_ADMIN_API_URL=https://api.example.com ./frontend
```

### 安全性提醒

Admin UI 走 **`ADMIN_PASSWORD` cookie session**：環境變數設定後，所有 `/admin/*` 路由與 admin API 都需先登入；未設則跳過驗證（**僅限本機開發**）。生產建議再加：

- 部署到內網 / VPN，僅授權 IP 可存取
- 前置 reverse proxy（nginx / caddy / traefik）加 TLS
- Cloudflare Access / Tailscale / 類似的 zero-trust 閘道

CORS 預設仍為 `allow_origins=["*"]`（見 CODE_REVIEW.md §C1）— 即使有 admin auth，仍不建議直接面向公網。

### 執行測試

```bash
# DB / API / cost 單元測試
uv run pytest tests/test_db.py tests/test_api.py tests/test_cost.py
# 預期輸出：53 passed in ~1.0s

# Agent system（profile / tools / business hours / realtime）
uv run pytest tests/test_agent_system.py
# 預期輸出：34 passed
```

### API 快速參考

| 路徑 | 用途 |
|---|---|
| `GET /health` | 健康檢查 |
| `POST /api/admin/login` | ADMIN_PASSWORD cookie 登入 |
| `POST /api/admin/logout` | 清除 session cookie |
| `GET /api/profiles` | 列出 profiles（預設只顯示 active） |
| `POST /api/profiles` | 建立新 profile |
| `PATCH /api/profiles/{id}` | 更新 profile 設定（含 config JSON） |
| `DELETE /api/profiles/{id}` | Soft-delete（`is_active=false`） |
| `GET /api/sessions?status=&profile_id=&limit=&offset=` | 分頁列出 sessions（response 含 `X-Total-Count` header） |
| `GET /api/sessions/{id}` | Session 詳情（含 raw_report，舊 row 自動 backfill cost） |
| `GET /api/sessions/{id}/events` | Session 逐筆事件 |
| `GET /api/sessions/{id}/livekit-link` | LiveKit Cloud 錄音頁連結 |
| `GET /api/stats/profiles` | 各 profile 累計統計 |
| `GET /api/stats/daily` | 每日統計 |
| `GET /api/deploy/status` | LiveKit Cloud agent 狀態 + secrets |
| `GET /api/deploy/logs?log_type=deploy\|build` | Agent 執行 / build log 快照 |
| `POST /api/deploy/deploy` | 觸發 `lk agent deploy` |
| `POST /api/deploy/switch-profile` | 切換 AGENT_PROFILE secret |
| `POST /api/test/start` | 起本機 connect-mode agent（admin Try 按鈕用） |
| `DELETE /api/test/stop/{room}` | 停掉本機測試 agent |

### Admin 主要功能

- **Sessions** — 分頁列表（10/25/50）、Profile/Status/Mode filter；detail 頁有 Conversation chat bubble（function call 折疊）/ Metrics 表 / Raw events tabs
- **Profiles** — 結構化編輯器（Display/Agent name、Language、Timezone、Welcome message + 給 realtime 用的 Welcome instructions、Instructions、Tools multi-select、Operator 折疊區）+ Advanced JSON 給未涵蓋欄位
- **Deploy** — LiveKit Cloud agent 狀態 / Active profile 切換 / Secrets 列表 / 帶 level 著色的 deploy / build logs
- **Cost** — Realtime 使用 Gemini Live audio + text token + 快取 + Deepgram STT 一起計算；舊 session 自動 backfill
