# Code Review Report — Agent Management Platform MVP

**Scope:** Phase 1–5（DB / Agent 整合 / Management API / Admin UI / 維運體驗）
**Test status:** 53/53 passed（`tests/test_db.py`、`tests/test_api.py`、`tests/test_cost.py`）
**Review date:** 2026-04-16
**Round 2 review:** 2026-04-17（整合 Copilot / Codex 審查）
**Round 3 update:** 2026-04-28（admin auth + sessions/deploy UX + Gemini Live cost）

---

## 1. 整體評估

| 面向 | 評分 | 備註 |
|---|---|---|
| 架構清晰度 | 優 | 三層清楚：`db/` ↔ `api/` ↔ `frontend/app/admin/`，YAML→DB 優雅過渡 |
| 型別安全 | 優 | SQLAlchemy 2.0 + Pydantic v2 + TS 都有完整 annotation |
| 測試覆蓋 | 良 | DB / API / cost 共 53 unit；`agent.py` entrypoint 仍需 LiveKit mock 略過 |
| 錯誤處理 | 良 | Agent 端 bare except 改 `logger.exception`；API 端 404/409 + admin auth |
| 安全性 | 良 | CORS 已修正；admin password-gated auth（`ADMIN_PASSWORD` env） |
| 可部署性 | 良 | docker-compose 含 agent + api + frontend；data / profiles volume 持久化 |
| 維運體驗 | 良 | sessions pagination + Gemini Live cost + deploy logs 清楚 |

---

## 修復進度總覽

### Round 1（2026-04-16）— 原始 Code Review

| # | 問題 | 嚴重度 | 狀態 |
|---|---|---|---|
| C1 | CORS `*` + credentials 衝突 | Critical | ✅ 已修 — `allow_credentials=False`，支援 env 覆蓋 |
| C2 | cost prefix-match bug | Critical | ✅ 已修 — `sorted(key=len, reverse=True)` |
| C3 | session_events 沒寫入 DB | Critical | ✅ 已修 — events_buffer + chat_history flush |
| M1 | 崩潰 session 卡 running | Major | ✅ 已修 — `mark_stale_sessions()` + lifespan reconciler |
| M2 | duration_seconds 永遠 None | Major | ✅ 已修 — wall-clock 計算 |
| M3 | `_db_profile_id` 污染 config | Major | ✅ 已修 — tuple 回傳 |
| M4 | bare except 吞錯誤 | Major | ✅ 已修 — `logger.exception()` |
| M5 | deps.py 多餘 init_db | Major | ✅ 已修 — 移除 |
| M6 | 測試隔離不完整 | Major | ✅ 已修 — conftest.py `:memory:` |

### Round 2（2026-04-17）— Copilot / Codex 審查

| # | 問題 | 嚴重度 | 狀態 |
|---|---|---|---|
| R2-1 | DB session 未 rollback | Critical | ✅ 已修 — `db.rollback()` before `close()` |
| R2-2 | livekit-link URL 未 encode | Critical | ✅ 已修 — `urllib.parse.quote()` |
| R2-3 | 管理 API 無認證 | Critical | ✅ 已修 — `X-Admin-Token` header + env 開關 |
| R2-5 | events + session 寫入非原子 | Moderate | ✅ 已修 — `add_events` 去掉 commit，由 `complete_session` 統一 commit |
| R2-7 | PATCH 過濾用 `is not None` 不精確 | Moderate | ✅ 已修 — `model_dump(exclude_unset=True)` |
| R2-8 | `update_profile` 無欄位白名單 | Minor | ✅ 已修 — `_UPDATABLE_FIELDS` 白名單 |
| CX-1 | 停用 profile 仍 fallback 到 YAML | Moderate | ✅ 已修 — 停用的 profile 拋出 ValueError |

### 確認為已修或誤報的項目

| 項目 | 判定 |
|---|---|
| Copilot #4：`profile_stats_endpoint` 全表載入 | ✅ 已用 SQL `GROUP BY` |
| Copilot #6：engine singleton 非線程安全 | ✅ 實際風險低：`lifespan` 在接受 request 前已 init |
| Codex #2：API 啟動時不跑 YAML import | ✅ **誤報**，lifespan 已呼叫 `import_yaml_profiles` |

### Round 3（2026-04-28）— Admin 體驗 + Cost 計算

| # | 主題 | 結果 |
|---|------|------|
| R3-1 | ADMIN_PASSWORD-gated 驗證 | ✅ 取代「無認證」狀態 — 所有 admin API 需帶 cookie；前端 `/admin/login` 流程 |
| R3-2 | Connect-mode 本地 agent 管理 | ✅ `testApi.start/stop` + `/api/test/*` — Try 按鈕統一走本機 connect-mode |
| R3-3 | Sessions 列表分頁 + Mode 欄位 | ✅ X-Total-Count header + 10/25/50 page size + realtime/pipeline badge |
| R3-4 | Sessions detail 結構化呈現 | ✅ Usage / Cost cards + Conversation/Metrics/Raw tabs（function call 折疊） |
| R3-5 | Deploy logs 體驗 | ✅ 解釋卡 + 空狀態 + 行級著色 + Open in Cloud |
| R3-6 | Gemini Live cost 計算 | ✅ realtime 拆 audio_in/out + text_in/out + cached + Deepgram STT |
| R3-7 | agent_mode 欄位 + 輕量 migration | ✅ Session DB schema 加欄位；舊 row heuristic 推導；不重啟自動補欄位 |
| R3-8 | Dark mode select 可讀性 | ✅ `bg-transparent` → `bg-background text-foreground` |
| R3-9 | UIUX_REVIEW 13 項全部完成 | ✅ 詳見 UIUX_REVIEW.md |

---

## 2. Critical（上 prod 前必修）

### C1. CORS 設定違反 spec — ✅ 已修
`api/main.py` — 預設 `allow_credentials=False`，設 `ADMIN_API_CORS_ORIGINS` env 時改為明確 origins + credentials=True。

### C2. 成本費率匹配邏輯有 prefix-match bug — ✅ 已修
`db/cost.py` — `_match_llm_rate()` / `_match_rate()` 都用 `sorted(key=len, reverse=True)` 最長優先匹配。

### C3. Session events 完全沒寫入 DB — ✅ 已修
`agent.py` — `events_buffer` 在 `_on_metrics_collected` 收集 metric，`log_usage()` 時追加 chat_history，統一 flush。

### R2-1. DB session 未 rollback — ✅ 已修（Round 2 新增）
`api/deps.py:21` — `finally` 區塊只有 `db.close()`，未先 rollback。若 request handler 拋出異常且有未提交的髒資料，SQLAlchemy session 可能殘留不一致狀態。已加 `db.rollback()` before `close()`。

### R2-2. livekit-link URL 未 encode — ✅ 已修（Round 2 新增）
`api/routes_sessions.py:94-96` — `room_name` 和 `project` 直接嵌入 URL string，含空格或特殊字元時 URL 損壞。已加 `urllib.parse.quote()`。

### R2-3. 管理 API 無認證 — ✅ 已修（Round 2 新增）
`api/deps.py` 新增 `require_admin` dependency，透過 `X-Admin-Token` header 驗證。
- 未設 `ADMIN_API_TOKEN` env → 跳過驗證（開發環境）
- 有設 → 所有 `POST/PATCH/DELETE /api/profiles` 需帶 token
- 讀取端 (`GET`) 不受影響

---

## 3. Major / Moderate

### M1. 崩潰的 agent 永遠卡在 running — ✅ 已修
`db/session_store.py:mark_stale_sessions()` + `api/main.py` lifespan reconciler。

### M2. duration_seconds 永遠 None — ✅ 已修
`agent.py` — wall-clock `(now - started_at).total_seconds()`。

### M3. DB profile 被污染 `_db_profile_id` — ✅ 已修
`agent_factory.py` — tuple 回傳 `(config, db_profile_id)`。

### M4. bare except 吞錯誤 — ✅ 已修
`agent_factory.py` / `agent.py` — 改 `logger.exception(...)`。

### M5. deps.py 多餘 init_db — ✅ 已修

### M6. 測試隔離不完整 — ✅ 已修
`tests/conftest.py` — `AGENT_DB_PATH=:memory:`。

### R2-5. events + session 寫入非原子 — ✅ 已修（Round 2 新增）
`db/session_store.py:add_events()` 原本自己 `db.commit()`，再由 `complete_session()` 做第二次 commit。進程若在兩次 commit 之間崩潰，事件已寫入但 session 仍是 running。

修法：`add_events()` 移除 `db.commit()`，改為只做 `db.add_all(rows)`。`complete_session()` 的 `db.commit()` 成為唯一提交點，確保 events + session 狀態原子寫入。測試中直接呼叫 `add_events` 的地方已補上 `db.commit()`。

### R2-7. PATCH 過濾不精確 — ✅ 已修（Round 2 新增）
`api/routes_profiles.py:79` — `if v is not None` 會讓明確傳送的 `display_name=""` 被過濾掉，也無法區分「未傳」vs「傳了 None」。改用 `payload.model_dump(exclude_unset=True)` 只更新客戶端實際傳送的欄位。

### CX-1. 停用 profile 仍 fallback 到 YAML — ✅ 已修（Round 2 新增）
`agent_factory.py` — DB 中 `is_active=False` 的 profile 原本會跳到 YAML fallback，若同名 YAML 檔存在就等於 soft-delete 失效。現在停用的 DB profile 直接拋出 `ValueError`，不再 fallback。

---

## 4. Minor

| # | 問題 | 檔案 | 狀態 |
|---|---|---|---|
| m1 | 前端 profile 編輯器會顯示 `_db_profile_id` | `frontend/app/admin/profiles/[id]/page.tsx` | ✅ M3 已修根因 |
| m2 | `/?profile=${profile.name}` 未 URI-encode | 同上 | ✅ R3-2 改成 connect-mode 啟動，已不再用此路徑 |
| m3 | Dashboard `limit: 10` 但 `.slice(0, 5)` | `frontend/app/admin/dashboard/page.tsx` | ✅ 已修 |
| m4 | Sessions 頁無 pagination UI | `frontend/app/admin/sessions/page.tsx` | ✅ R3-3 已實作 |
| m5 | `== True` + noqa | `db/profile_store.py:15` | 待修（不影響行為） |
| m6 | `ProfileCreate.display_name` 預設 `""` | `api/schemas.py` | 待修（前端 form 已強制非空） |
| m7 | `daily_stats_endpoint` Python 端聚合 O(N) | `api/routes_stats.py` | MVP 可接受 |
| m8 | admin 頁 loading flash | `frontend/app/admin/*` | ✅ skeleton loader 已上 |
| m9 | 原生 `confirm()`/`alert()` 對話框 | UIUX_REVIEW P0 #3 | ✅ 改用 sonner toast + ConfirmDialog |
| m10 | livekit-link URL pattern 猜的 | `api/routes_sessions.py` | ✅ R2-2 已加 URL encode |
| R2-8 | `update_profile` 無欄位白名單 | `db/profile_store.py` | ✅ 已修 |

---

## 5. Nits

- `db/__init__.py` 匯出 `Session` 會與 SQLAlchemy `Session` 命名衝突 — 建議 rename model 為 `AgentSession`
- `db/engine.py:reset_singletons` 只為測試存在，但測試沒用到，可刪或加 `_for_tests` 前綴
- 計畫書承諾的 Monaco JSON editor 目前是 `<textarea>` — MVP 可接受

---

## 6. 安全性檢查

| 風險 | 目前狀態 | 建議 |
|---|---|---|
| 認證 / 授權 | ✅ ADMIN_PASSWORD cookie session（R3-1） | 透過 `ADMIN_PASSWORD` env 開啟；前端 `/admin/login` |
| CORS | ✅ `*` + credentials=False | 已修正符合 spec |
| SQL injection | 全走 ORM | OK |
| JSON deserialize | `json.loads` + `yaml.safe_load` | OK |
| Rate limit | 無 | 內網 OK；外網需加（FastAPI-limiter） |
| XSS / CSRF | session cookie 是 `HttpOnly` + SameSite | OK |
| 密鑰外洩 | 所有 key 經 env | OK |
| 日誌洩漏 | `log_usage` 印 summary | summary 可能包含 PII；部署時注意 log pipeline |

---

## 7. 測試報告

```
tests/test_db.py   — 17 tests  (profile_store, session_store, yaml_import)
tests/test_api.py  — 18 tests  (health, profiles CRUD, sessions 404, stats empty, admin auth)
tests/test_cost.py — 18 tests  (LLM/STT/TTS pipeline + realtime Gemini Live + Deepgram STT)
TOTAL              — 53 passed in ~1.0s
```

**Coverage gap（已改善）：**
- ~~`db/cost.py` — 0 tests~~ → ✅ 18 個測試（含 5 個 realtime case）
- `agent_factory.load_profile_from_db` — 未驗證 DB↔YAML fallback
- `agent.py` entrypoint — 需要 LiveKit mock，屬可接受略過
- `routes_stats` 非空資料聚合 — 目前只測 empty case
- Frontend — 改用 Playwright 對 production build 做 smoke test（人工觸發，未自動化）

---

## 8. 修復歷程

### Round 1 修復（commit `88ad308`, `1917476`）
| # | 改動 | 狀態 |
|---|---|---|
| C1 | CORS `*` + credentials | ✅ |
| C2 | cost prefix-match + 測試 | ✅ |
| C3 | 寫 session_events | ✅ |
| M1–M6 | 6 項 Major | ✅ |

### Round 2 修復（2026-04-17）
| # | 改動 | 檔案 |
|---|---|---|
| R2-1 | DB session rollback | `api/deps.py` |
| R2-2 | URL encoding | `api/routes_sessions.py` |
| R2-3 | Admin API key auth | `api/deps.py`, `api/routes_profiles.py` |
| R2-5 | 原子 events+session write | `db/session_store.py`, `agent.py` |
| R2-7 | PATCH exclude_unset | `api/routes_profiles.py` |
| R2-8 | update_profile 白名單 | `db/profile_store.py` |
| CX-1 | 停用 profile 不 fallback | `agent_factory.py` |

### Round 3 修復（2026-04-22 ~ 2026-04-28）— Admin UX + Cost
| # | 改動 | 檔案 |
|---|---|---|
| R3-1 | ADMIN_PASSWORD cookie session | `api/deps.py`, `api/routes_auth.py`, `frontend/app/admin/login/page.tsx` |
| R3-2 | Connect-mode 本地 agent 管理 | `api/routes_test.py`, `frontend/lib/admin-api.ts` |
| R3-3 | Sessions pagination + Mode 欄位 | `api/routes_sessions.py`, `db/session_store.py`, `frontend/app/admin/sessions/page.tsx` |
| R3-4 | Sessions detail 結構化 | `frontend/app/admin/sessions/[id]/page.tsx` |
| R3-5 | Deploy logs UX | `frontend/app/admin/deploy/page.tsx` |
| R3-6 | Gemini Live + Deepgram cost | `db/cost.py`, `agent.py`, `tests/test_cost.py` |
| R3-7 | agent_mode column + migration | `db/models.py`, `db/engine.py`, `db/session_store.py` |
| R3-8 | Dark mode select 修正 | `frontend/app/admin/**` |
| R3-9 | UIUX_REVIEW 13 項 | 詳見 `UIUX_REVIEW.md` |

---

## 9. 結論

經過三輪 review 和修復，所有 Critical / Major / Moderate 問題均已解決。

剩餘 Minor 項目（m5、m6）為微調，不影響功能。平台品質已從「可 demo」提升至「可內網生產 + 維運人員可長期使用」等級。上 prod 必要條件：

1. `ADMIN_PASSWORD` env 必須設定（未設時 admin 路由開放）
2. 透過網路層（VPN / reverse proxy）限制訪問，因 CORS 還是 `*`
3. 若 agent 部署在 LiveKit Cloud 而非本機，需設 `AGENT_DB_URL` 共享資料庫（否則 cloud session 不會出現在本機 admin UI）
