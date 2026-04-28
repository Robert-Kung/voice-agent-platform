# Voice Agent Workshop — 專案現況

> 最後更新：2026-04-28

---

## 專案架構總覽

```
voice-agent-workshop/
├── agent.py              Agent worker 入口（profile 載入 + LiveKit session）
├── agent_factory.py      DB / YAML → 動態 Agent class 組裝
├── agent_tools.py        模組化 Tool Registry（8 個內建 tool 工廠）
├── profiles/             場域定義（YAML，作為 DB 初始化的 seed）
│   ├── car_inspection.yaml    汽車代檢中心
│   ├── dental_clinic.yaml     幸福牙醫診所
│   └── restaurant.yaml        好食光餐廳
├── api/                  Management API（FastAPI）
│   ├── main.py                lifespan + middleware + routers
│   ├── routes_profiles.py     Profile CRUD
│   ├── routes_sessions.py     Session 查詢 + cost backfill
│   ├── routes_deploy.py       lk CLI wrapper（status/logs/deploy/switch-profile）
│   ├── routes_test.py         Connect-mode 本地 agent 管理（admin Try）
│   ├── routes_auth.py         ADMIN_PASSWORD-gated cookie session
│   └── routes_stats.py        Dashboard 統計
├── db/                   SQLAlchemy 2.0 + 輕量 column migration
│   ├── models.py              Profile / Session / SessionEvent
│   ├── cost.py                Pipeline + Realtime（Gemini Live）成本計算
│   ├── profile_store.py       DB ↔ YAML 雙向同步
│   ├── session_store.py       Session lifecycle + filtered query
│   └── engine.py              Engine + 自動補欄位 migration
├── frontend/             Next.js + Admin UI
│   ├── app/admin/             Dashboard / Profiles / Sessions / Deploy
│   └── lib/admin-api.ts       型別化 API client
├── tests/
│   ├── test_db.py             17
│   ├── test_api.py            18（含 admin auth）
│   ├── test_cost.py           18（含 Gemini Live + Deepgram realtime）
│   └── test_agent_system.py   34（profile / tools / business hours / lookup_qa）
├── docker-compose.yml    agent + api + frontend + 共享 data volume
├── livekit.toml          Cloud 部署設定
└── pyproject.toml        Python 依賴
```

---

## 核心設計：Profile-based 動態 Agent

### 運作原理

YAML profile 定義一個場域的所有內容：
- `instructions` — Agent 的系統 prompt
- `welcome_message` — 進線歡迎語
- `tools` — 該 Agent 要掛載的 tools（每個 profile 可不同）
- `services` — 營業時間規則（配合 `check_business_status` tool）
- `qa_data` — FAQ 關鍵字資料庫（配合 `lookup_qa` tool）

### 可用 Tools

| Tool | 用途 | 使用場景 |
|------|------|---------|
| `get_current_datetime` | 取得當前日期時間 | 通用 |
| `check_business_status` | 判斷營業狀態 | 有營業時間的場域 |
| `lookup_qa` | 關鍵字搜尋 FAQ | 有 FAQ 資料庫的場域 |
| `transfer_to_human` | 轉接真人 | 需要轉接機制的場域 |
| `check_weather` | 查詢天氣 | 戶外活動相關 |
| `search_menu` | 搜尋菜單 / 產品目錄 | 餐廳、零售 |
| `book_appointment` | 預約登記 | 診所、美容美髮 |
| `calculate_price` | 費用查詢 | 有價目表的場域 |

### 各 Profile 的 Tool 配置差異

| Tool | 車容坊 | 牙醫 | 餐廳 |
|------|:---:|:---:|:---:|
| `get_current_datetime` | ✓ | ✓ | ✓ |
| `check_business_status` | ✓ | ✓ | ✓ |
| `lookup_qa` | ✓ | ✓ | ✓ |
| `transfer_to_human` | ✓ | ✓ | ✓ |
| `check_weather` | ✓ | — | — |
| `book_appointment` | — | ✓ | — |
| `search_menu` | — | — | ✓ |
| `calculate_price` | — | — | ✓ |

---

## 部署方式一：本地 Console / 本地前端（開發 & Demo）

### 使用方式

```bash
# Console 模式（純語音終端，最快測試）
uv run agent.py console --profile car_inspection
uv run agent.py console --profile restaurant
uv run agent.py console -p dental_clinic

# 環境變數指定
AGENT_PROFILE=restaurant uv run agent.py console
```

```bash
# 搭配本地前端
cd frontend && pnpm dev   # http://localhost:3000
# agent 另一個終端
uv run agent.py dev
```

### Profile 切換方式

| 方式 | 說明 |
|------|------|
| CLI `--profile` / `-p` | 命令列直接指定 |
| 環境變數 `AGENT_PROFILE` | `.env` 或 shell 設定 |
| 前端 URL `?profile=restaurant` | 透過 `/api/token` route 注入 room metadata |

### 前端 Profile 切換原理（僅限本地開發 `npm run dev`）

```
瀏覽器 ?profile=restaurant
  → /api/token (route.ts, dev only)
  → roomConfig.metadata = '{"profile":"restaurant"}'
  → JWT → LiveKit Cloud → Room 建立
  → agent entrypoint: ctx.job.room.metadata → 讀取 profile
```

⚠️ **注意**：`/api/token` route 有 `NODE_ENV !== 'development'` 保護，production build 會直接報 500。這是故意的安全設計（該 route 不做 auth）。

### 適用情境

- 開發階段快速迭代
- 內部 demo（筆電接投影 / 分享螢幕）
- 測試新 profile 的 prompt / tools 邏輯

---

## 部署方式二：LiveKit Cloud（`lk agent deploy`）

### 使用方式

```bash
# 部署 agent 到 Cloud（程式碼有異動時）
lk agent deploy

# 透過 Dashboard Playground 或 Sandbox 測試
# https://cloud.livekit.io → project → Agent Playground
```

### 部署資訊

| 項目 | 值 |
|------|-----|
| Cloud subdomain | `first-live-demo-vuid06vq` |
| Agent ID | `CA_TKHBUEw7z6YK` |
| Agent name | `voice-assistant` |
| 部署命令 | `lk agent deploy` |

### Cloud Secrets 管理

> ⚠️ `.env` 只在本地 `uv run` 時讀取，**不會自動上傳**到 Cloud。
> Cloud 環境需用 `lk agent update-secrets` 獨立設定。
> `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` 由 Cloud 自動注入，不需上傳。

| Secret | 預設值 | 必要性 | 說明 |
|--------|--------|:---:|------|
| `AGENT_NAME` | `voice-assistant` | 不需上傳 | 程式碼 hard-coded，免費版固定一個 |
| `AGENT_PROFILE` | `car_inspection` | ✅ 已設 | 場域選擇 |
| `AGENT_MODE` | `realtime` | ✅ 已設 | 預設 realtime；設 pipeline 改走 LiveKit Inference |
| `GOOGLE_API_KEY` | — | ✅ 已設 | Realtime 模式必要；值見 `.env` |
| `GOOGLE_REALTIME_VOICE` | `Kore` | 可選 | 不設使用預設值 |
| `GOOGLE_REALTIME_MODEL` | `gemini-2.5-flash-native-audio-preview-12-2025` | 可選 | 不設使用預設值 |

**完整上傳 secrets 指令（realtime 模式）：**

```bash
# 1. deploy 程式碼
lk agent deploy

# 2. 上傳 secrets（GOOGLE_API_KEY 值從 .env 複製，勿貼入文件）
lk agent update-secrets \
  --secrets "AGENT_MODE=realtime" \
  --secrets "AGENT_PROFILE=car_inspection" \
  --secrets "GOOGLE_API_KEY=<從 .env 複製>"
```

**Pipeline 模式（不需 Google API Key）：**

```bash
lk agent deploy
lk agent update-secrets \
  --secrets "AGENT_MODE=pipeline" \
  --secrets "AGENT_PROFILE=car_inspection"
```

**何時需要 deploy vs 只更新 secrets：**

| 改了什麼 | 需要 deploy | 需要 update-secrets |
|---------|:-----------:|:--------------------:|
| `agent.py` / `agent_factory.py` / `agent_tools.py` 程式碼 | ✅ | ❌ |
| `profiles/*.yaml` 內容 | ✅ | ❌ |
| 只切換環境變數（profile、mode、voice…） | ❌ | ✅ |
| 兩者都改 | ✅ | ✅ |

### Profile 切換方式

| 方式 | 說明 | 是否可用 |
|------|------|:---:|
| `lk agent update-secrets` | 只更新 env，30 秒重啟，**不需重新打包** | ✅ 最快 |
| `lk agent deploy --secrets` | 重新打包部署並指定 env | ✅ |
| Room metadata（自架前端） | 前端建 room 時注入，每次連線可不同 | ✅（需自架） |
| Dashboard Playground | LiveKit 內建 UI | ❌ 無法注入 metadata |
| Sandbox | LiveKit 管理的 endpoint | ❌ 不認識自訂 profile 欄位 |

### 切換 Profile 的實際指令

```bash
# ★ 最快：只改 env，不重新打包（約 30 秒生效）
lk agent update-secrets --secrets "AGENT_PROFILE=restaurant"
lk agent update-secrets --secrets "AGENT_PROFILE=dental_clinic"
lk agent update-secrets --secrets "AGENT_PROFILE=car_inspection"

# 確認目前狀態
lk agent status

# 看 log 確認 profile 有載入
lk agent logs
# log 中應看到：Session using profile: 好食光餐廳 (restaurant)
```

### 其他常用指令

```bash
# 查看目前設定的 secrets（只顯示 key）
lk agent secrets

# 回滾到上一個版本
lk agent rollback

# 查看所有部署版本
lk agent versions

# 重啟（不改程式碼）
lk agent restart
```

### 免費版限制

- 免費版只能部署 **一個 agent**
- `agent_name` 固定為 `"voice-assistant"`，所有 profile 共用
- 切換 profile 優先用 `lk agent update-secrets`（最快，約 30 秒）

### Cloud 部署的 Profile 決定流程

```
entrypoint(ctx)
  ├─ 1. ctx.job.room.metadata → {"profile": "restaurant"}  ← 自架前端可用
  ├─ 2. ctx.job.metadata  → dispatch metadata                ← API dispatch 可用
  └─ 3. AGENT_PROFILE env → "car_inspection"（預設）          ← 一定可用
                              ↑ 透過 update-secrets 修改
```

---

## 測試

### 單元測試（53 個 admin / cost / db / api，~1 秒；agent_system 34 個需修 fixture）

```bash
uv run pytest tests/test_db.py tests/test_api.py tests/test_cost.py
# → 53 passed in ~1.0s
```

| 測試類別 | 數量 | 驗證內容 |
|---------|:----:|---------|
| TestDB | 17 | profile_store / session_store / yaml_import |
| TestAPI | 18 | health / profiles CRUD / sessions / stats / admin auth |
| TestCost (pipeline) | 13 | LLM prefix-match / TTS chars / STT minutes / 總和 |
| TestCost (realtime) | 5 | Gemini Live audio+text 拆分、cached 折扣、Deepgram STT 補上 |

### 既有 agent_system 測試（34 個）

```bash
uv run pytest tests/test_agent_system.py
```

涵蓋 ProfileLoading / ToolRegistry / BusinessStatus / LookupQA / AgentClassCreation / ToolIsolation / SearchMenuTool / CalculatePriceTool / AgentMode（realtime/pipeline 切換 + RealtimeModel 建構）。
此 suite 預設讀 host DB（`profiles` table），需先 `uv run python -m db.migrate` 才能跑。

### 實機測試

| 方式 | 命令 | 測試範圍 |
|------|------|---------|
| Console | `uv run agent.py console -p restaurant` | 語音對話完整流程 |
| 本地前端 | `pnpm dev` + `?profile=xxx` | 前端 UI + 語音 |
| Cloud | `lk agent deploy` + Dashboard | 部署 + 雲端運行 |

---

## Admin 管理平台

### Pages

| 路徑 | 用途 |
|------|------|
| `/admin/login` | ADMIN_PASSWORD 登入 |
| `/admin/dashboard` | 概覽：active profiles、running/total sessions、total cost、最近 session |
| `/admin/profiles` | Profile 列表（search、show inactive、tools chip、Edit / Try / Deactivate / Reactivate） |
| `/admin/profiles/[id]` | Profile 編輯（結構化欄位 + tools multi-select + welcome_instructions + Advanced JSON） |
| `/admin/profiles/new` | 新建 profile（與 detail 共用元件） |
| `/admin/sessions` | 列表 + 分頁（10/25/50）+ Mode 欄位 + Profile/Status filter |
| `/admin/sessions/[id]` | Detail：Status/Mode/Duration/Cost/Started cards + Usage / Cost cards + Conversation/Metrics/Raw tabs |
| `/admin/deploy` | LiveKit Cloud agent 狀態、profile activation、build/deploy logs |

### Cost 計算（db/cost.py）

| 模式 | 計算來源 | 單價 |
|------|---------|------|
| Pipeline | `llm_prompt/completion_tokens` × LLM rate + `stt_audio_duration` × `stt_rate` + `tts_characters_count` × `tts_rate` | 由 model name 匹配 |
| Realtime | `llm_input_audio/text_tokens` + `llm_output_audio/text_tokens` + cached + `stt_audio_duration` × Deepgram nova-2 | Gemini Live: \$3 / \$12 / \$0.5 / \$2 / \$0.075（per 1M）；Deepgram \$0.0043/min |

Realtime 架構固定為 Deepgram STT → Gemini Live LLM/TTS（text-input 模式避免延遲遞增 bug）。費率寫死於 `_REALTIME_STT_RATE_PER_MIN` 與 `REALTIME_RATES`，未來如需切其他組合再放開。

### Connect-mode 本地測試流程

`/admin/profiles` 列表頁的 `Try` 按鈕、`/admin/profiles/[id]` 詳細頁的 `Try (本機)` 按鈕，皆呼叫 `POST /api/test/start`：
- API 起一個 `uv run agent.py connect --room <test-{profile}-{uuid}>` 的子行程
- 自動拼出 LiveKit room URL 並開新分頁讓使用者連線測試
- 行程結束 / 使用者點 stop 時 `POST /api/test/stop/{room}` 清理

這條路徑跑的是 **DB 最新的** profile，不受 LiveKit Cloud deploy 是否最新影響 — 適合做 prompt 微調的快速 iterate。要實際上線到 Cloud，走 `/admin/deploy` 或 profile detail 的 `Deploy →` 按鈕。

---

## 待解決議題

### ~~議題 1：Cloud 部署的動態 Profile 切換~~ ✅ 已解決

**解決方式**：

1. 三個 profile YAML 已加入 git 版控（移除 `.gitignore` 排除規則）並重新 deploy
2. 切換 profile 只需 `lk agent update-secrets`，約 30 秒生效，不需重新打包

```bash
# 切換場域（30 秒生效）
lk agent update-secrets --secrets "AGENT_PROFILE=restaurant"
lk agent update-secrets --secrets "AGENT_PROFILE=dental_clinic"
lk agent update-secrets --secrets "AGENT_PROFILE=car_inspection"
```

**注意**：若新增或修改 profile YAML 內容，仍需 `lk agent deploy` 重新打包。

### 議題 2：Google Real-time API 介接 ✅ 已完成

**現況**：Realtime 模式本地 & Cloud 均可正常運作，前端網頁測試通過。

**已完成**：
- [x] 評估 Google Real-time API 作為 STT+LLM+TTS 一體方案的可行性
- [x] 與 LiveKit Agent 框架的介接方式（`livekit-plugins-google` 的 `RealtimeModel`）
- [x] SDK 升級至 1.4.6（向前相容，無需重構既有程式碼）
- [x] 雙模式 session 建立（`AGENT_MODE=pipeline|realtime`）
- [x] 單元測試新增 6 個（共 34 個全通過）
- [x] 修正 model 名稱（需用 `gemini-2.5-flash-native-audio-preview-12-2025`，不可用 3.x 版本）
- [x] 修正 voice 名稱（Gemini 不支援 `Nova`，預設改為 `Kore`）
- [x] Tool calling 延遲優化（`NON_BLOCKING` + `WHEN_IDLE`，避免靜音等待與截斷）
- [x] 實機測試歡迎語與 tool 呼叫正常運作
- [x] Cloud secrets 上傳成功（`GOOGLE_API_KEY`、`AGENT_MODE`、`AGENT_PROFILE`）
- [x] 前端網頁 profile 切換測試通過

**架構**：
- **Pipeline 模式**：STT → LLM → TTS（LiveKit Inference，無需額外 API key）
- **Realtime 模式（生產採用）**：Deepgram nova-2 STT → 文字輸入 Gemini Live → 直接生成語音
  - 採用「TextInputRealtimeModel」繞過 Gemini Live 純音訊輸入會 token 累積導致延遲遞增（1s → 30s+）的 bug
  - 詳見第二週進展：external VAD + STT + EOU + 覆寫 `on_user_turn_completed`
  - 需 `GOOGLE_API_KEY` + `DEEPGRAM_API_KEY`

**Realtime 模式關鍵設定**：

| 參數 | 值 | 說明 |
|------|-----|------|
| model | `gemini-2.5-flash-native-audio-preview-12-2025` | Live API 專用模型；chat 模型不可用 |
| voice | `Kore`（預設） | Gemini 聲音；OpenAI 聲音名稱（如 Nova）不相容 |
| `tool_behavior` | `NON_BLOCKING` | tool 執行期間模型說橋接語，不靜音 |
| `tool_response_scheduling` | `WHEN_IDLE` | 說完當前語音才插入 tool 結果，避免截斷 |
| VAD | 內建（不加外部 VAD） | Gemini Live 有內建 VAD；加 silero 反而衝突 |

> **為何不用 Gemini 3.1？** LiveKit 官方文件記載 `gemini-3.1-flash-live-preview` 有已知相容性問題：
> - `send_client_content` 在第一輪對話後被 API 拒絕（1007 錯誤），這是我們最初遇到的根本原因
> - `generate_reply()`、`update_instructions()`、`update_chat_ctx()` 與 3.1 不相容（呼叫被忽略）
> - **非同步 function calling（NON_BLOCKING）3.1 不支援**，只有 2.5 支援
> - 官方正在調查長期修復方案，目前維持 2.5

**切換方式**：
```bash
# 本地測試
AGENT_MODE=realtime uv run agent.py console -p car_inspection

# 切換 voice
GOOGLE_REALTIME_VOICE=Charon AGENT_MODE=realtime uv run agent.py console -p car_inspection

# Cloud 部署（GOOGLE_API_KEY 值從 .env 取得，勿寫入文件）
lk agent update-secrets --secrets "AGENT_MODE=realtime" --secrets "GOOGLE_API_KEY=<從 .env 複製>"
```

**已完成**：
- [x] 延遲 & 品質 A/B 比較（Pipeline vs Realtime）— 採用 realtime
- [x] 決定正式上線模式：realtime + text-input 架構
- [x] Gemini Live 中文發音（多音字「檢」、「行」）對抗策略 — 走「源頭詞彙去歧義」（完整詞組）
- [x] car_inspection 發音問題收斂

**架構固定**：mode 不再是 profile-level 設定，固定 worker AGENT_MODE=realtime。詳見 `db/cost.py` 開頭註解與計畫書 4/27 紀錄。

### 議題 3：SIP 電話介接 🔧 進行中

**現況**：Inbound 電話已可介接。✅

**完成**：
- [x] SIP trunk 供應商確認
- [x] LiveKit SIP Inbound 介接設定
- [x] Inbound 通話可正常進入 agent

**待辦**：
- [ ] SIP + profile 切換聯合測試（不同電話號碼 → 不同場域）
- [ ] 電話號碼與 profile 的對應機制實作（如需要）
- [ ] Outbound 電話撥打（如有需求）

---

## 新增 Profile 快速指引

```bash
# 1. 複製模板
cp profiles/restaurant.yaml profiles/my_store.yaml

# 2. 編輯 YAML（instructions, tools, services, qa_data）
# 3. 測試
uv run agent.py console --profile my_store

# 4. 部署
AGENT_PROFILE=my_store lk agent deploy
```

## 新增 Tool 快速指引

在 `agent_tools.py` 中：

```python
def make_my_tool(profile: dict, config: dict):
    @function_tool
    async def my_tool(self, param: str) -> dict:
        """Tool 描述（LLM 看到的）"""
        return {"result": "..."}
    return my_tool

TOOL_REGISTRY["my_tool"] = make_my_tool
```

在 YAML profile 中宣告：

```yaml
tools:
  - name: my_tool
    config:
      key: value
```
