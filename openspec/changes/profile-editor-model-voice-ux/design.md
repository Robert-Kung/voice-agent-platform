## Context

Graph 三部曲已 archive，runtime 端能力齊備：`multi-model-runtime` 讓 profile config 的 `models` 區塊（`mode` / `llm` / `stt` / `tts` / `realtime`）驅動 session 組裝；`graph-runtime-executor` 讓 `editor_mode: graph` 的 profile 在 pipeline mode 下以 SDK 原生 handoff 執行。但 Profile Editor 前端停在 graph-agent-builder 落地時的狀態：模型 / 語音沒有編輯 UI（只能靠 deployment secret / YAML），且殘留「graph 執行待 executor 落地」的過期文案。

現況技術棧：Next.js admin UI，split-panel 版面（中央 prompt 永遠可見 + 右側折疊面板 + graph canvas 用 React Flow/xyflow）；`useProfileForm` hook 管表單狀態與 `buildConfig`/`splitConfig` round-trip；`lib/agent-graph.ts` 為純函數（vitest 已建）；`KnownConfig` 已含 `models`。後端 `routes_profiles` 已有 graph×realtime 422 與 `models` 區塊 Pydantic 驗證。

研究參考（2026-06-17）：Dograh AI 把 realtime vs pipeline 做成 model config 的「引擎模式 tabs」(Speech-to-Speech / BYOK)，並有 searchable VoiceSelector（語言/性別 badge + 試聽）；Pathors 則把模型完全藏起來、只暴露 executionMode。兩家都採「global 常駐 + per-stage 分支」而非二選一。本設計採 Dograh 的引擎模式 tabs，但保留我們既有的 split-panel（prompt 永遠可見，優於 Dograh 的 node-config modal）。

## Goals / Non-Goals

**Goals:**
- 在 profile 編輯器內提供模型選擇 UI，以引擎模式 tabs（Realtime / Pipeline）讀寫既有 `models` 區塊，含模式限制與 graph×realtime 互斥的就地回饋。
- 提供語音設定（realtime free-form / pipeline TTS）綁到 `models`。
- UI 以版面 affordance 呈現「global 常駐底層、graph 選用分支層」的心智模型。
- （過期文案 + `tool_result_condition` parity 已拆至 `graph-editor-execution-status-fix`，非本 change goal。）

**Non-Goals:**
- 變數 / 資料蒐集 UI（v1 已移除 `variable_keys`，留待後續 change）。
- per-node 模型 UI（後端為 interface point；本次不做）。
- 版本 / rollback、test suites、AI 生成 graph 草稿。
- 任何 runtime 行為改動（模型解析、graph 執行皆已 archive）；後端最多微調既有 `models` 驗證，不新增 runtime 路徑。

## Decisions

### D1. 引擎模式以 tabs 呈現，tab = `models.mode`
採 Dograh 的 Realtime / Pipeline 兩 tab，選 tab 即設 `models.mode`。Realtime tab 顯示 `models.realtime`（model/voice/thinking）；Pipeline tab 顯示 `models.stt` / `models.tts` / `models.llm` 三段 provider+model selector。
- **為何不用單一表單列 mode dropdown + 全部欄位**：realtime 與 pipeline 的欄位幾乎不重疊（realtime 無獨立 TTS/STT pipeline、pipeline 無 thinking），同框會讓一半欄位永遠 disabled，認知負擔高。tab 天然分隔兩種互斥形狀。
- **替代方案**：Pathors 式「藏起模型只給 executionMode」——否決，與我們「自控 runtime / 自選模型」的定位相反，也浪費已落地的 multi-model 能力。

### D2. 預設值以「compiled default（標 inherited）」顯示，不強制寫入
`models` 缺欄位時 UI 顯示 built-in 編譯預設並標為 inherited（vs pinned），但**不**自動寫入 config（避免把隱式預設變成顯式 pin，破壞 multi-model-runtime「未宣告即 fallback」的非破壞性契約）。只有使用者主動改才寫入。
- **review 修正（autoplan）**：原寫「effective default」是誇大——realtime 預設受部署 env（`GOOGLE_REALTIME_MODEL`/`VOICE`）shadow，前端看不到。改用「compiled default，部署 env 可覆蓋」，並區分 inherited/pinned。見 review 報告 cross-phase theme 1。
- **替代方案**：load 時把預設灌滿 config——否決，會讓每個 profile 存檔後都釘死當下預設，未來改 built-in 預設不會自動套用。

### D3. realtime 限制在 UI 層硬約束，後端仍是真相
Realtime tab 的 LLM 只給 Gemini Live 變體（封裝後），不提供非 Gemini realtime provider；known-dead 變體不可選。這對齊 `model-provider-runtime`「realtime 非 Gemini 直接 reject」與 `profile-model-config` 的 Gemini Live variant allowlist。前端做就地約束純為 UX，存檔時後端 Pydantic（含 variant allowlist）仍是強制 gate。

### D4. graph×realtime 互斥：editor_mode 硬性 gate 引擎選擇（決議 2026-06-17）
`editor_mode: graph` 時，**Realtime tab 直接 disabled/locked**（inline 說明 graph 需 pipeline），realtime 在 UI 上不可達、Pipeline 是唯一可選引擎。這是**輸入層 affordance，不是前端 save-gate**——後端 422 仍是唯一真相、涵蓋 API/YAML 繞過路徑，前端不攔截 save 假驗證（延續「前端 validateGraph 僅 UX」的職責邊界）。轉 graph 時若原本是 realtime，跳 confirm 並於確認時把 `models.mode` 切成 pipeline，不留 graph+realtime 不可存狀態。422 仍會在繞過情況回來，就地呈現為「graph×realtime 互斥」而非泛用 save error。

> 取捨：先前草案是「軟性警告（可選到再跳警告）」。改硬性鎖 tab，因為讓使用者選到一個必被 422 拒的組合再警告，體驗比直接鎖差；鎖 tab 屬輸入引導、不違背後端為真相。

**與已 ship 的 `graph-editor-execution-status-fix` banner 的對齊（re-review 2026-06-17）**：該 fix 的中央 banner 在 graph 模式依 `models.mode` 條件化——pipeline 顯示原生執行、realtime 顯示「降級攤平」。但 graph profile **存不了 realtime**（422），所以 in-editor 選 Realtime 的真相是「不可存」而非「會降級」。本 change 落地引擎 tabs 後，graph + realtime 的 in-editor 狀態由本 D4 的 exclusivity 警告**取代**（非疊加）那條降級 banner；降級文案只保留給「部署層 `AGENT_MODE` env 覆蓋一個已存成 pipeline 的 graph profile」這條 deploy-time 路徑。spec 對齊：本 change 補一份 `graph-editor-ux` 的 MODIFIED delta 把這個優先序寫進「Deployment-aware execution status」scenario，owner 收斂到本 capability 的「Graph and realtime exclusivity feedback」。

### D5 / D6 → 已拆至 `graph-editor-execution-status-fix`（autoplan D-T3）
過期 banner（依 profile 宣告 mode 條件化、結果優先文案、註明 `AGENT_MODE` 可覆蓋）與 `validateGraph` 的 `tool_result_condition` parity warning 屬純 hygiene、與本 feature 無耦合，已切到獨立 change 先 ship。本 change 不再含這兩項。

### D7. 元件落點：header Stack chip 點開面板（autoplan D-T2）
模型 / 語音 stack 由 header 既有的 Stack summary chip **點開 popover/panel** 承載，而非塞進右側折疊面板第 5 個槽（design review：折疊槽=最低發現性，而模型/語音是成本/延遲/語言最高風險設定）。chip 落地後顯示 profile 宣告的實際 stack（取代現況 `deployment-defined`）。
- **為何不放 node inspector**：模型/語音是 profile 級（global），非 per-node；屬 global 常駐底層。per-node 模型未來再進 inspector。
- **為何不塞右側折疊區**：見上；header chip 已存在、是最自然入口。

## Risks / Trade-offs

- **[realtime 變體 allowlist 前後端易漂移]** → 前端 allowlist 應從單一來源取（理想是後端暴露的常數 / endpoint），避免硬編在兩處。若本次先硬編，design 與 task 標注「與 `profile-model-config` 的 variant allowlist 對齊」並留 follow-up。
- **[effective-default 顯示與實際 runtime 解析不一致]** → 顯示的「預設」必須真的等於 runtime 的 built-in fallback；以 `resolve_session_components` 的預設為準，前端不可自行假設另一組預設值。
- **[provider/model 清單來源]** → 前端需要可選 provider/model 清單。若無現成 endpoint，最小做法是前端維護一份對齊 `KNOWN_DIRECT_PROVIDERS` + inference gateway 的靜態清單，並標注 follow-up 改為後端供給。
- **[過期文案漏改]** → 文案散落多處（中央 banner、SaveConfirmModal、header badge）；以 grep `graph-runtime-executor` / `fallback` 全面盤點，確保無遺漏。header 的「需 pipeline 部署」badge 本身仍正確，保留。
- **[graph×realtime 前端不硬擋可能讓使用者撞 422]** → 接受；後端為真相，前端就地警告已足夠降低踩雷率，硬擋反而與「前端僅 UX」邊界衝突。

## Migration Plan

- 純前端為主、無 DB migration（`models` 為 free-form config 既有欄位）。
- 部署：`docker compose up -d --build` 重建 frontend；後端若微調 `models` 驗證一併重建 api。
- Rollback：前端 revert 即可；無資料形狀變更，舊 profile config 不受影響（未宣告 `models` 照常 fallback）。
- 驗證：vitest 純函數（validateGraph 新 warning、models round-trip）+ 瀏覽器 QA（引擎 tab 切換寫對 `models.mode`、語音選擇 round-trip、graph 模式文案依 mode 正確、graph+realtime 存檔被 422 並正確呈現）。

## Open Questions

> autoplan review 已把前兩題升級為 gate 上的 taste decision（D-T1 / D-T2），見下方 GSTACK REVIEW REPORT。以下保留原始記錄。

- **[→ D-T1，gate 待裁]** provider/model 清單與預設權威來源：唯讀後端 endpoint vs 前端硬編 + contract 測試。review 強烈傾向 endpoint（否則重蹈本 change 要修的 parity-drift）。
- 語音 sample playback：標延伸；且本 repo **無 voice catalog 來源**，v1 改 free-form realtime + provider/model pipeline TTS，metadata/試聽延後（spec 已改）。
- **[→ D-T2，gate 待裁]** header Stack chip 顯示 `deployment-defined`：模型 UI 落地後改顯示 profile 宣告 stack？與 Stack 面板落點（chip popover / 常駐頂部 / Advanced 漸進揭露）一併在 gate 決定。

---

## GSTACK REVIEW REPORT (autoplan, 2026-06-17)

Codex unavailable → all voices `subagent-only` (single independent Claude reviewer per phase). DX phase skipped (admin GUI, not a dev SDK/CLI surface). Restore point: `~/.gstack/projects/Robert-Kung-first-livekit/main-autoplan-restore-20260617-103335.md`.

### Consensus tables (single-voice; no Codex to confirm)

**CEO:** premises CONCERN (defer-variables vs graph-implies-slot-filling) · right-problem CONCERN (model UI demand asserted not shown) · scope CONCERN (bundles hygiene + debatable feature) · alternatives CONCERN (Pathors-hide dismissed on positioning) · competitive FAIL (matching Dograh on model-tabs while Retell/Vapi win on no-config) · 6-month CONCERN (hardcoded list + invisible default).

**Design:** info-hierarchy 5/10 (Stack buried in 5th accordion) · mental-model 6/10 (global framing in copy not layout) · state-coverage 3/10 (load/empty/error/disabled/dirty/422 unspecified) · interaction-fit 7/10 (tabs right, but silent mode-mutate trap) · copy 5/10 (jargon-first) · specificity 6/10 (voice fields vague).

**Eng:** architecture CONCERN (effective-default not faithfully achievable; voice catalog absent) · tests CONCERN (no allowlist parity guard) · parity PASS (tool_result_condition matches exactly, no other drift) · edge-cases CONCERN (tab-wipe, AGENT_MODE honesty) · backend-risk CONCERN ("micro-tune Pydantic" trapdoor) · deploy/rollback PASS (pure FE, no migration).

### Cross-phase themes (flagged independently by 2+ phases — high confidence)
1. **Model-list / default source-of-truth** (Eng#1,#2 + CEO F3,F4): "effective default" is env-shadowed and a hardcoded FE list recreates the very parity-drift bug this change fixes. → drove spec relabel + new source-of-truth requirement + D-T1.
2. **Voice picker has no data source / field mapping vague** (Eng#8 + Design#6): no catalog exists. → v1 free-form realtime + provider/model pipeline TTS; metadata deferred.
3. **Banner honesty re AGENT_MODE override** (Eng#6 + Design#5): editor can't know runtime path. → softened spec + consequence-first copy.

### Auto-decided (mechanical → applied to artifacts)
| # | Phase | Decision | Principle |
|---|-------|----------|-----------|
| 1 | Eng/Design | Relabel "effective default"→"compiled default (deployment env may override)"; mark inherited vs pinned | P1 completeness |
| 2 | Eng/Design | Tab-switch keep-but-don't-clear inactive `models` sub-block + round-trip test | P1/P5 |
| 3 | Design | `models.mode` change = strategy change → confirm-on-save (mirror editor_mode) | P5 explicit |
| 4 | Design | Missing-states matrix (realtime-disabled, dirty, 422 surface, loading/error) | P1 |
| 5 | Eng/Design | Voice v1: free-form realtime + provider/model pipeline TTS; map exact `models.*`; defer catalog/playback | P1/P3 |
| 6 | Eng | Add allowlist parity contract test; sync realtime variant ↔ cost rate | P1 |
| 7 | Eng | Backend = hard non-goal (no runtime/validator edits); only read-only endpoint permitted | P5 |
| 8 | Eng/Design | Banner/confirm copy consequence-first; spec stops asserting actual runtime path | P5 |
| 9 | Design | Global-as-base-layer via layout affordance, not copy; +preserve-across-convert test | P1/P5 |
| 10 | Eng | parity test: `trigger:undefined`+condition → no warn | P1 |

### Surfaced to user (taste + strategy) — see final gate
- **D-T1** read-only `/api/admin/model-defaults` endpoint now vs hardcode+contract-test (frontend-only).
- **D-T2** Stack/voice placement: header-chip popover vs always-expanded top section vs progressive-disclosure "Advanced" toggle.
- **D-T3** split the change: ship hygiene (banners+parity) now, gate stack/voice UI — vs ship together.
- **Strategy flag (variables)** CEO: deferring variables leaves graphs half-exposed (slot-filling). User locked "defer" — flagged, not auto-reversed.
- **Strategy flag (demand)** CEO: validate model-UI demand with a design partner before the big build.
