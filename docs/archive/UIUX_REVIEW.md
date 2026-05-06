# Admin UI/UX Review

**初次 review**：2026-04-20（範圍：profiles 三頁）
**第二輪擴充**：2026-04-27 ~ 04-28（範圍擴及 sessions / deploy）
**測試方式**：Playwright + 1440×900 viewport，搭配原始碼 review

---

## 結論摘要

初版 admin 是「工程師工具」 — 手刻 JSON、原生 `prompt()` / `confirm()`、無欄位驗證。經過兩輪迭代，已達到「客服 lead / PM 可日常使用」的水準：profiles 結構化編輯、sessions 分頁與 conversation 視覺化、deploy logs 可讀、Gemini Live cost 透明。

**第一輪（profiles 三頁）13 項全數完成**。**第二輪（sessions / deploy）11 項全數完成**。剩餘僅技術 backlog（model 多樣化、Monaco editor）已放至 PROJECT_STATUS.md「未來目標」。

---

## 第一輪（profiles 三頁，2026-04-20 提出）

### 🔴 P0 — 嚴重影響使用者體驗

### 1. 用 `prompt()` 輸入 profile name — ✅ 已修
- **位置**：[frontend/app/admin/profiles/[id]/page.tsx:58](frontend/app/admin/profiles/[id]/page.tsx#L58)
- **問題**：建立新 profile 時跳出瀏覽器原生 `prompt()`，無法驗證格式 / 提示衝突 / 樣式化，行動裝置體驗差。
- **修法**：`name` 提升為表單第一個欄位，加 `^[a-z][a-z0-9_]*$` pattern hint 與 inline 驗證；`display_name` 為第二欄。

### 2. 整個 config 是一坨 JSON textarea — ✅ 已修
- **位置**：[frontend/app/admin/profiles/[id]/page.tsx:115-122](frontend/app/admin/profiles/[id]/page.tsx#L115-L122)
- **問題**：[`profiles/dental_clinic.yaml`](profiles/dental_clinic.yaml) 顯示 config 有結構化欄位（`agent_name` / `language` / `timezone` / `welcome_message` / `instructions` / `tools[]` / `human_operator_*`）。讓使用者手刻 JSON：
  - 易打錯逗號 / 引號，save 才報錯
  - 沒有 syntax highlight、line number
  - tools 是物件陣列，看不出有哪些可選工具
- **建議（依工程量遞增）**：
  - **MVP（採用）**：拆成多個欄位 — `Display Name` / `Agent Name` / `Language (select)` / `Timezone (select)` / `Welcome Message (textarea)` / `Instructions (textarea, 長)` / `Tools (multi-select checkbox)` / `Human Operator` 折疊區塊。多餘欄位放進「Advanced JSON」accordion。
  - **Better**：用 Monaco Editor / CodeMirror 取代 `<textarea>`，至少 JSON syntax highlight + 即時驗證。
  - **Best**：用 JSON Schema 自動產生表單（react-jsonschema-form）。

#### Monaco Editor vs JSON Schema → 自動表單

| 面向 | Monaco Editor | JSON Schema 自動表單 |
|------|--------------|----------------------|
| 定位 | 更好的 textarea | 不寫 JSON，改用表單 |
| 使用者看到 | 還是 JSON 文字，但有 highlight、錯誤紅線、補全 | 結構化欄位（input / select / array add 按鈕） |
| 學習門檻 | 仍需懂 JSON | 不需懂 JSON |
| 彈性 | 任何 JSON 都能編 | 受 schema 約束 |
| 適合 | 工程師、power user | 客服 / 業務 |
| Bundle size | 大（~2MB，需 lazy load） | 中（~200KB） |

**採用策略（已落地）**：MVP 拆欄位 — `Display Name` / `Agent Name` / `Language (select)` / `Timezone (select)` / `Welcome Message` / `Welcome Instructions`（realtime 用）/ `Instructions` / `Tools (multi-select checkbox)` / `Operator` 折疊區。多餘欄位放進「Advanced JSON」accordion。Monaco / JSON Schema 自動表單暫不實作。

### 3. `confirm()` / `alert()` 原生彈窗 — ✅ 已修
改用 `sonner` toast + 自製 `ConfirmDialog` 元件。

---

### 🟡 P1 — 一致性與可用性

### 4. Tools 欄位過長把 row 撐爆 — ✅ 已修
改用 chip 樣式，超過 3 個顯示「+N more」可展開。

### 5. 沒有 search / filter / pagination — ✅ 已修（profiles 加 search；sessions 加 search + 分頁）

### 6. 列表沒有「Edit」/「Try」按鈕 — ✅ 已修
profiles row actions：Edit / Try / Deactivate / Reactivate。

### 7. 無 unsaved-changes 警告 — ✅ 已修
useMemo dirty-snapshot 比對 + `beforeunload` listener。

### 8. 沒有 inactive profile 的 reactivate 按鈕 — ✅ 已修

### 9. `Deactivate` 紅色按鈕沒有 hover affordance — ✅ 已修
border + background hover。

---

### 🟢 P2 — 細節打磨

### 10. Profile detail 頁標題只有 `name` — ✅ 已修
標題改為 `display_name`（大）+ `name` (mono, 小) + `id`。

### 11. Loading state 純文字 — ✅ 已修（skeleton loader）

### 12. 表頭欄位被 wrap — ✅ 已修（`whitespace-nowrap`）

### 13. `toLocaleString()` 不同 locale 不同格式 — ✅ 已修
顯示文字統一 `YYYY-MM-DD HH:mm`（`formatDate` 共用 util）；tooltip 保留 `toLocaleString` 提供完整資訊。

---

## 第二輪（sessions / deploy / cost，2026-04-27 ~ 04-28）

### 🔴 阻塞性問題

### S1. Sessions list 無分頁 — ✅ 已修
- 後端 `X-Total-Count` header + 前端 10 / 25 / 50 page size + Prev/Next
- 計數顯示「Showing 1-25 of 38」

### S2. Sessions detail 全用 `<pre>{JSON}</pre>` 看不出所以然 — ✅ 已修
- Status / Mode / Duration / Total Cost / Started 五張卡
- Usage Summary 4-card grid（LLM input/output 拆 audio + text + cached、STT、TTS）
- Cost Breakdown 顯示 LLM + STT 金額 + per-rate 明細
- 三個 tab：Conversation chat bubble / Metrics 摘要表 / Raw JSON

### S3. Conversation 中的 `FunctionCall(...)` repr 看不懂 — ✅ 已修
- FunctionCall / FunctionCallOutput 行不再用 chat bubble，改成置中的 `<details>` 摺疊
- 預設只顯示「→ tool_name (tool call)」一行；點開才看完整 repr

### D1. Deploy logs 顯示 `Using agent [CA_xxx]` 看不懂 — ✅ 已修
- 加說明卡：deploy = 執行時 stdout / build = 上次 deploy build 輸出
- 空狀態偵測：只有 selector echo 時顯示「目前無近期 log，發起一次測試後再回來看」
- 行級 level 著色（error/warn/debug/default）
- 「Open in Cloud ↗」link 直連 LiveKit Dashboard

### 🟡 一致性與可用性

### S4. Sessions 列表缺 Mode 欄位 — ✅ 已修
- DB Session 加 `agent_mode` 欄位 + 輕量 migration
- 舊 row 用 audio_tokens heuristic 推導 realtime/pipeline
- 列表顯示 realtime（紫）/ pipeline（青）badge

### S5. 三個 select 在 dark mode 看不見 — ✅ 已修
`bg-transparent` → `bg-background text-foreground`，連 profiles search、profile detail Language/Timezone/Advanced JSON 一起改。

### S6. Try 行為兩處不一致（list 走 connect-mode、detail 卻是 URL link） — ✅ 已修
- Profile detail 「Try (本機)」按鈕也走 `testApi.start`
- 多一顆「Deploy →」按鈕導去 `/admin/deploy?profile=<name>`，deploy 頁讀 query param 自動選該 profile

### 🟢 細節打磨

### S7. Realtime cost 漏算 Deepgram STT — ✅ 已修
原本 realtime 只算 Gemini Live LLM，漏掉 text-input 架構必經的 Deepgram nova-2。樣本 session：$0.0268 → $0.0334。

### S8. Dashboard / Recent Sessions 日期格式不一致 — ✅ 已修
共用 `formatDate` util。

### S9. Agent Name 下方 hint「LiveKit WorkerOptions 用」字 wrap — ✅ 已修
改為「LiveKit worker 識別名稱（agent_name）」。

### D2. Deploy 頁首屏 ~6s 全空白 — 🚧 部分（仍為單一 skeleton block，未拆三區獨立 loading）
- 已加 lastFetched timestamp + refresh 按鈕作為次選
- 後續可拆 Agent / Active profile / Logs 各自 loading 進階優化

---

## 未做的（已歸入 backlog）

| # | 項目 | 為什麼不做 |
|---|------|------------|
| P0 #2 Better | Monaco editor for Advanced JSON | MVP 拆欄位已涵蓋日常編輯需求，Monaco 約 +2MB bundle 不划算 |
| P0 #2 Best | JSON Schema 自動表單 | schema 還在演化，過早抽象化 |
| 模型 / mode 切換 | Profile-level agent_mode | 架構決策 — 維持 worker 全 realtime（詳見 PROJECT_STATUS.md 議題 2） |
| Per-provider 費率 | 寫進 profile YAML | 既然 mode 固定 = Deepgram + Gemini Live，費率寫死於 `db/cost.py` 即可 |
| ColorScheme floater 蓋住內容 | — | 確認是設計刻意（hover 才現），不改 |
