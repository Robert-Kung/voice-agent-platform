# Code Review Report — Agent Management Platform MVP

**Scope:** Phase 1–4 (DB / Agent 整合 / Management API / Admin UI)
**Branch:** `claude/agent-management-platform-23G5e`
**Commits 涵蓋:** `77df22a` → `2981c36`
**Test status:** 27/27 passed (`tests/test_db.py`, `tests/test_api.py`)
**Review date:** 2026-04-16

---

## 1. 整體評估

| 面向 | 評分 | 備註 |
|---|---|---|
| 架構清晰度 | 優 | 三層清楚：`db/` ↔ `api/` ↔ `frontend/app/admin/`，YAML→DB 優雅過渡 |
| 型別安全 | 優 | SQLAlchemy 2.0 + Pydantic v2 + TS 都有完整 annotation |
| 測試覆蓋 | 可 | Phase 1-3 unit 測試完整；Phase 2 (agent.py 整合) 未測；`db/cost.py` 未測 |
| 錯誤處理 | 可 | Agent 端 try/except 太寬鬆會吞噬問題；API 端 404/409 OK |
| 安全性 | 需注意 | CORS 設定有 spec 違規；MVP 無認證（符合計畫，但需部署時 firewall） |
| 可部署性 | 未完成 | docker-compose 尚未加 api service（Phase 5 待做） |

---

## 2. Critical（上 prod 前必修）

### C1. CORS 設定違反 spec — 瀏覽器會拒絕帶 cookie 請求
`api/main.py:32-38`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 與 credentials=True 不能共存
    allow_credentials=True,
    ...
)
```

CORS spec 規定 `Access-Control-Allow-Origin: *` 時 `Access-Control-Allow-Credentials: true` 會被瀏覽器拒絕。目前 admin UI 沒帶 cookie 所以 OK，但一旦加登入就會壞。

**修法：** 設為明確 origins，或把 `allow_credentials=False`。

### C2. 成本費率匹配邏輯有 prefix-match bug — 算出來的錢是錯的
`db/cost.py:71-74`

```python
for model_key, rates in LLM_RATES.items():
    if model_key.lower() in llm_model.lower():
        rate = rates
        break
```

Dict 迭代順序中 `google/gemini-2.5-flash` 在 `google/gemini-2.5-flash-lite` **之前**，所以當 `llm_model="google/gemini-2.5-flash-lite"` 傳進來，會先 match 到 `gemini-2.5-flash` → 用錯費率（`0.15/0.60` 而非 `0.075/0.30`）。**OpenAI 同病**：`openai/gpt-4o` 在 `gpt-4o-mini` 之前會誤 match。

**修法：** 按 key 長度倒排，優先匹配最長 prefix：
```python
for model_key in sorted(LLM_RATES, key=len, reverse=True):
    if model_key.lower() in llm_model.lower():
        rate = LLM_RATES[model_key]
        break
```

### C3. Session events 完全沒寫入 DB
`agent.py:269-306`

計畫書 §4.2 寫「批次寫入 `session_events`」，但 `agent.py` 裡只有 `complete_session()`，**沒有任何 `session_store.add_events()` 呼叫**。結果：
- `session_events` table 永遠是空的
- `/admin/sessions/[id]` 的 Events 區塊永遠顯示「No events recorded」
- Transcript / tool_call / metric 事件無法追溯

**修法：** 在 `_on_metrics_collected` 裡 batch 收集 metric events，於 `log_usage()` 時 flush 進去；並加入 `session.history.items` 的 user/agent 訊息。

---

## 3. Major

### M1. 崩潰的 agent 永遠卡在 `running` status
`agent.py:266-306`

`ctx.add_shutdown_callback(log_usage)` 只在「正常」shutdown 時觸發。若 worker crash / OOM / 被 kill，`sessions.status` 永遠停在 `"running"`。

**建議：** API 啟動時跑 reconciler：
```sql
UPDATE sessions SET status='failed', shutdown_reason='stale'
WHERE status='running' AND started_at < NOW() - INTERVAL 1 HOUR;
```

### M2. `duration_seconds` 永遠是 `None`
`agent.py:291`

```python
duration_seconds=summary.get("duration", None),
```

`UsageCollector.get_summary()` 的 key 是 `llm_prompt_tokens` / `tts_characters` / `stt_audio_duration` 等，**沒有 `duration` 欄位**。應自行計算：
```python
duration = (datetime.now(timezone.utc) - started_at).total_seconds()
```

### M3. DB profile 被污染 `_db_profile_id` key
`agent_factory.py:65`

```python
data["_db_profile_id"] = profile.id
```

若 admin UI 透過 PATCH 把整個 `config` 存回去，`_db_profile_id` 就會被持久化到 `config_json`，之後每次讀都累積。改用 tuple 回傳：
```python
def load_profile(name: str) -> tuple[dict, str | None]:
    return (config, db_profile_id)
```

### M4. 所有 DB 操作都被 bare except 吞掉
`agent_factory.py:51, 68`, `agent.py:33, 181, 303`

```python
except Exception:
    return yaml_names  # 完全沒 log
```

DB 壞掉時 silent fallback 到 YAML，UI 顯示錯的 profile，運維無感知。改成 `logger.exception(...)`。

### M5. `api/deps.py` 在每個 request 呼叫 `init_db()`
`api/deps.py:13`

已在 lifespan 做過，這裡可移除（idempotent 但浪費）。

### M6. DB engine singleton 在測試隔離不完整
`db/engine.py:14-15`

全域 `_engine` / `_session_factory`。若測試誤呼 `get_session_factory()` 會污染 `data/agent_platform.db`。建議 `conftest.py` 設 `AGENT_DB_PATH=:memory:`。

---

## 4. Minor

| # | 問題 | 檔案 |
|---|---|---|
| m1 | 前端 profile 編輯器會顯示 `_db_profile_id`（關聯 M3） | `frontend/app/admin/profiles/[id]/page.tsx` |
| m2 | `/?profile=${profile.name}` 未 URI-encode | 同上 :144 |
| m3 | Dashboard `limit: 10` 但 `.slice(0, 5)` — 浪費 5 筆 | `frontend/app/admin/dashboard/page.tsx:19,122` |
| m4 | Sessions 頁無 pagination UI，寫死 `limit: 100` | `frontend/app/admin/sessions/page.tsx` |
| m5 | `== True` + noqa，可改 `q.filter(Profile.is_active)` | `db/profile_store.py:15` |
| m6 | `ProfileCreate.display_name` 預設 `""`，改 `None` 更明確 | `api/schemas.py` |
| m7 | `daily_stats_endpoint` 在 Python 端聚合，O(N) 記憶體 | `api/routes_stats.py` |
| m8 | 所有 admin 頁都是 `'use client'` + fetch on mount，造成 loading flash | `frontend/app/admin/*` |
| m9 | `confirm()` / `prompt()` / `alert()` 為原生對話框 | MVP 可接受 |
| m10 | `livekit-link` URL pattern 是猜的，未驗證 | `api/routes_sessions.py:91-97` |

---

## 5. Nits

- `db/__init__.py` 匯出 `Session` 會與 SQLAlchemy `Session` 命名衝突 — 建議 rename model 為 `AgentSession`
- `db/engine.py:reset_singletons` 只為測試存在，但測試沒用到，可刪或加 `_for_tests` 前綴
- 計畫書承諾的 Monaco JSON editor 目前是 `<textarea>` — MVP 可接受

---

## 6. 安全性檢查

| 風險 | 目前狀態 | 建議 |
|---|---|---|
| 認證 / 授權 | 無 | MVP 決策；上線前必須 firewall / VPN / reverse-proxy basic auth |
| CORS | `*` + credentials | 見 C1 |
| SQL injection | 全走 ORM | OK |
| JSON deserialize | `json.loads` + `yaml.safe_load` | OK |
| Rate limit | 無 | 內網 OK；外網需加（FastAPI-limiter） |
| XSS / CSRF | API 無 cookie + React escape | OK |
| 密鑰外洩 | 所有 key 經 env | OK |
| 日誌洩漏 | `log_usage` 印 summary | summary 可能包含 PII；部署時注意 log pipeline |

---

## 7. 測試報告

```
tests/test_db.py  — 15 tests  (profile_store, session_store, yaml_import)
tests/test_api.py — 12 tests  (health, profiles CRUD, sessions 404, stats empty)
TOTAL             — 27 passed in 3.17s
```

**Coverage gap:**
- `db/cost.py` — 0 tests（C2 就是因為沒測才漏）
- `agent_factory.load_profile_from_db` — 未驗證 DB↔YAML fallback
- `agent.py` entrypoint — 需要 LiveKit mock，屬可接受略過
- `routes_stats` 非空資料聚合 — 目前只測 empty case
- Frontend — 無 Jest / Playwright；MVP 可接受

---

## 8. 建議修復優先級

| # | 改動 | 工時 | 風險 |
|---|---|---|---|
| 1 | C1 CORS 修 | 5 min | 0 |
| 2 | C2 cost prefix-match + 測試 | 20 min | 0 |
| 3 | C3 寫 session_events | 45 min | 中 |
| 4 | M2 duration_seconds 修 | 10 min | 0 |
| 5 | M3 `_db_profile_id` 拆出 | 15 min | 低 |
| 6 | M4 bare except → logger.exception | 15 min | 0 |
| 7 | M5 `api/deps.py` 移除 `init_db()` | 2 min | 0 |
| 8 | M1 stale session reconciler | 20 min | 低 |

**總計約 2-2.5 小時** 即可把 MVP 品質從「可 demo」推到「可內網生產」。

---

## 9. 結論

架構、分層、型別使用都做得漂亮；SQLAlchemy 2.0 + Pydantic v2 + Next 15 的搭配是現代的寫法；計畫書 → 實作高度對齊。

**主要缺陷集中在 Phase 2 的 agent 整合**：session_events 沒寫、duration 拿錯、cost prefix bug、profile 污染，合計會讓「demo 跑起來但資料都不對」。這 4 個點（C2/C3/M2/M3）修完，Phase 1-3 就是穩定的 MVP。

CORS / 無認證是已知的 MVP 取捨，**上 prod 前必須透過網路層解決**（內網 / VPN / reverse proxy basic auth），這在 Phase 5 部署文件中必須明記。
