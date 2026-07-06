# Architecture

LiveKit-based 語音 Agent 平台。Profile-driven，admin UI 管理 profile / 工具 / 部署 / sessions。

---

## 系統總覽

```
┌──────────────────────────────────────────────────────────────────┐
│                          USER (操作者 / 客戶)                     │
└────────────────┬─────────────────────────────────┬───────────────┘
                 │ Admin browser                   │ Voice (WebRTC / SIP)
                 ▼                                 ▼
        ┌──────────────────┐              ┌──────────────────┐
        │ Next.js Admin UI │              │ LiveKit Cloud    │
        │ :3004 /admin/*   │              │ Room / SFU       │
        └────────┬─────────┘              └────────┬─────────┘
                 │ REST                            │ Audio frames
                 ▼                                 ▼
        ┌──────────────────┐              ┌──────────────────┐
        │ FastAPI :8083    │              │ Agent Worker     │
        │ (api/)           │◀────────────▶│ (agent.py)       │
        │  profiles        │ DB           │  - profile load  │
        │  sessions        │ profile_store│  - LLM/STT/TTS   │
        │  deploy / test   │              │  - tool calls    │
        │  stats / tools   │              │  - session_report│
        └────────┬─────────┘              └────────┬─────────┘
                 │                                 │
                 └─────────────┬───────────────────┘
                               ▼
                    ┌──────────────────────┐
                    │ SQLite               │
                    │ data/agent_platform.db│
                    │  Profile / Session / │
                    │  SessionEvent        │
                    └──────────────────────┘
```

YAML profiles in `profiles/` are **fallback/seed** only — DB is source of truth once any admin edit happens. `db.migrate.import_yaml_profiles` only imports YAMLs missing from DB by name (idempotent, never overwrites).

---

## Profile 渲染管線

Admin UI 編輯的 profile 不是把所有東西塞進 tool；大部分結構化設定會在 agent 啟動時 render 進 system instructions。

```
profile.config_json (DB row)
        │
        ▼
┌───────────────────────────────────────────┐
│ agent_factory.create_agent_class(profile) │
└───────┬───────────────────────────────────┘
        │
        ├─► instructions    (raw)
        ├─► _render_qa_block       ──► 若 qa_mode=="inline"，QA 拼進 instructions
        ├─► _render_services_block ──► services dict 拼進 instructions
        ├─► welcome_message / welcome_instructions
        │
        ├─► build_tools_for_agent()
        │       │
        │       ├─► Tier 1：get_current_time（user opt-in）
        │       ├─► Tier 2：lookup_qa  (僅當 qa_mode=="tool" + qa_data)
        │       │           transfer_to_human (僅當 human_operator.enabled)
        │       └─► Tier 3：make_http_tool(...) for 每個自定義 HTTP tool
        │
        └─► dynamic Agent class (subclass of agents.Agent)
```

---

## 模型堆疊解析（`models` 區塊）

Profile 的 `models` 區塊宣告要用的 LLM / STT / TTS / 聲音 / 語言;`runtime.providers.resolve_session_components(profile, mode)` 在 `session.start` 前把它解析成實際 component。

```
models 區塊（或省略 → 編譯預設 runtime.constants.DEFAULT_*）
        │
        ▼
resolve_session_components(mode)
        │  每個 component 走 _build_with_preflight：
        │    normalize_spec（補 via=inference、保留 language/voice）
        │    → build_llm/stt/tts（via:inference 走 inference gateway；
        │      via:direct 走 provider plugin）
        │    → 單一 spec = 裸 component；spec 陣列 = FallbackAdapter
        │  pinned spec 建不起來 → 降級到編譯預設 + loud warning（SIP 無 fallback，絕不掛電話）
        ▼
ResolvedComponents(llm, stt, tts | realtime_llm, model_names→cost 層)
```

要點：

- **Catalog 是唯一真相**：`runtime.constants.MODEL_CATALOG`(provider/model 清單)、`SUGGESTED_VOICES`、`MODEL_LANGUAGES`(per-model 語言矩陣) 由 `api/routes_model_defaults` 吐給前端;`db.cost` 只標註 `priced` flag(不反推 catalog)。三份鏡像(constants / 前端 fixture / `model-catalog.ts` fallback)由 contract test 防漂移。
- **Catalog 經 gateway 驗證**：`tests/test_model_defaults.py::test_catalog_id_accepted_by_gateway`(opt-in `LIVEKIT_INFERENCE_PROBE=1`)對每個 catalog id 實打 gateway,確保「列得出來 = 跑得起來」。
- **語言矩陣是 advisory**:save 端只保證 spec 形狀,不擋語言(free-text escape hatch);Deepgram 專用 model(`nova-2-phonecall` 等)為英文 only,UI 會警告但不阻擋。
- **`via:direct` 受限**:`DIRECT_BUILDABLE = {(llm,google),(stt,deepgram)}`,save 端與 build 端共用同一份(`test_direct_buildable_matches_runtime` 確保兩邊不分歧)。
- **Realtime**:`TextInputRealtimeModel`(Gemini Live + 外部 Deepgram STT 文字輸入);僅 allowlist 內、可計費的 Gemini 變體;與 graph 互斥。詳見 [root README](../README.md) 的 realtime 說明。

---

## Tool 三層架構

> 規則：**Tier 1 不再增加新工具**，所有新業務需求走 Tier 3。

### Tier 1 — 內建原語（Python，使用者可選掛）

| 工具 | 用途 | 實作位置 |
|---|---|---|
| `get_current_time` | 取得目前時間 + 星期 | `agent_tools.py` |

### Tier 2 — Profile 設定 → 渲染進 instructions

不是 tool。Admin UI 提供結構化表單，render 階段把資料拼進字串，零延遲、無 round-trip。

| 設定 | 對應原 tool | 模式 |
|---|---|---|
| QA Database (`qa_data`) | `lookup_qa` | `qa_mode: inline`（拼字串）／ `tool`（保留 tool call） |
| Service Hours (`services`) | `check_business_status` | 永遠 inline render，搭 Tier 1 `get_current_time` 讓 LLM 自行判斷 |
| Human Operator (`human_operator.*`) | `transfer_to_human` | enabled=true 時自動掛 `transfer_to_human` factory |

### Tier 3 — 使用者自定義 HTTP 工具

Admin UI 直接新增「呼叫某個 API endpoint」的工具。一支通用 `make_http_tool` factory，從 profile config 動態建立 `@function_tool`（用 `raw_schema`）。

```yaml
tools:
  - name: report_elevator_failure
    description: 當住戶回報電梯故障時呼叫
    endpoint: https://your-api.com/elevator/report
    method: POST
    auth_header: "Bearer ${ELEVATOR_API_KEY}"
    timeout_seconds: 10
    response_mode: wait   # wait（預設）或 quick_ack
    parameters:
      - { name: building, type: string, required: true, description: 棟別 }
      - { name: symptom, type: string, description: 故障狀況 }
```

業務邏輯（送 LINE / 開單 / 寫 DB）住在使用者自寫的 API server，agent 平台只負責對話 + 呼叫。

#### Response mode（`response_mode`）

- **`wait`（預設）**：同步等待回應。timeout 時回傳 `{"success": false, "pending": true, "error": "timeout", "detail": ...}`，detail 指示 LLM：請求已送出、後端可能仍在處理、不要重複提交（避免 side effect 成功但回應慢時誤報失敗、誘發重複建單）。4xx/5xx 與連線錯誤維持 `{"success": false, "error": ...}`。
- **`quick_ack`**：fire-and-forget。請求以背景 task 送出，工具立即回 `{"success": true, "accepted": true, "detail": ...}`，消除語音 dead air。背景結果只記 log（成功 info / 失敗 warning），不回饋對話。適用於建單、通知類「必達型」API。

#### SSRF 防護（`agent_tools._validate_endpoint`）

下列 endpoint 會在 build-time 拒絕：

- 非 `http://` / `https://` scheme
- Hostname blocklist：`localhost`、`metadata`、`metadata.google.internal`、`169.254.169.254`
- IP 字面量解析後屬於：loopback / private (RFC1918) / link-local / multicast / reserved
- `${ENV_NAME}` 解析失敗（環境變數未設）

43 個專屬測試於 `tests/test_http_tool.py`。

---

## Session 生命週期

```
LiveKit room joined
        │
        ▼
session_store.create_session(room, profile_id) ─► row(status="running")
        │
        │ 通話進行中：metrics + transcript 進 SessionEvent
        │
        ▼
session ended (normal / error)
        │
        ├─ normal：session_store.complete_session()
        │           ├─ status="completed"
        │           ├─ duration_seconds
        │           ├─ raw_report_json (含 metrics)
        │           └─ total_cost_usd (db/cost.py)
        │
        └─ error：session_store.fail_session(reason)
                    └─ status="failed"

排程清理：session_store.mark_stale_sessions(max_age_hours=1)
          將 >1h 仍 "running" 的 row 標 failed（reason 含 "stale"）
```

成本計算（`db/cost.py`）：
- **Realtime mode** — Gemini Live audio + text token + cache + Deepgram STT
- **Pipeline mode** — LLM / STT / TTS 各自費率分開算

---

## 部署模式

| 模式 | 啟動 | 用途 |
|---|---|---|
| Console | `uv run agent.py console` | 本機 stdin/stdout 測對話 |
| Dev | `uv run agent.py dev` | 連 LiveKit Cloud 開發 project |
| Connect (test) | `POST /api/test/start` | Admin UI「Try」按鈕，本機 worker + Cloud room |
| Cloud | `lk agent deploy` | Production，AGENT_PROFILE env 控預設 profile |
| Docker | `docker compose up -d --build` | 本機跑 agent + api + frontend 三個 service |

---

## 主要目錄

```
voice-agent-workshop/
├── agent.py              Agent worker 入口（pipeline + realtime 雙模式）
├── agent_factory.py      動態 Agent class 組裝（profile → instructions + tools）
├── agent_tools.py        Tool factory registry + make_http_tool（Tier 3）
├── profiles/             YAML profile（DB seed / fallback）
│   ├── car_inspection.yaml    汽車代檢中心
│   ├── dental_clinic.yaml     幸福牙醫診所
│   ├── restaurant.yaml        好食光餐廳
│   ├── elevator_repair.yaml   電梯報修中心（Tier 3 POC）
│   └── example.yaml           樣版
├── api/                  FastAPI Management API
│   ├── main.py                lifespan + middleware + routers
│   ├── routes_profiles.py     Profile CRUD
│   ├── routes_sessions.py     Session 查詢 + cost backfill
│   ├── routes_tools.py        Tool 名稱列表（給 admin UI 提示）
│   ├── routes_deploy.py       lk CLI wrapper
│   ├── routes_test.py         Connect-mode 本地 agent 管理
│   └── routes_stats.py        Dashboard 統計
├── db/                   SQLAlchemy 2.0
│   ├── models.py              Profile / Session / SessionEvent
│   ├── cost.py                Pipeline + Realtime 成本計算
│   ├── profile_store.py       DB CRUD
│   ├── session_store.py       Session lifecycle + filter query
│   ├── migrate.py             tables + import_yaml_profiles (idempotent)
│   └── engine.py              singleton engine + session factory
├── frontend/             Next.js 14 admin UI
│   └── app/admin/
│       ├── (authenticated)/   登入後 layout (sidebar) + Dashboard / Profiles / Sessions / Deploy
│       └── login/             無 sidebar 的登入頁（route group 外）
├── tests/                pytest（147 passed）
│   ├── test_db.py
│   ├── test_api.py
│   ├── test_cost.py
│   ├── test_http_tool.py      43 SSRF + factory tests
│   └── test_agent_system.py   profile / tools / qa modes / human operator
├── docs/
│   ├── ARCHITECTURE.md   ← 本文件
│   └── archive/          歷史 review / plan（不再維護）
├── docker-compose.yml
├── livekit.toml
└── pyproject.toml
```
