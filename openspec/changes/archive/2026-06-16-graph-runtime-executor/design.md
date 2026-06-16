## Context

`graph-agent-builder`（已歸檔）落地了 `graph-agent-schema`：profile config 的 `graph` 區塊（`schema_version`、`global_prompt`、`nodes`、`edges`）與 `editor_mode` 開關，並在每次存檔時把 graph 攤平回 `instructions`（`graphToPrompt`）。`multi-model-runtime`（已歸檔）落地了 `resolve_session_components(profile, mode)`，把模型元件與 cost 模型名解析出來。

目前 runtime（`agents/agent.py` 的 `entrypoint` + `agents/agent_factory.py` 的 `create_agent_class`）**只認得單一 `instructions` 字串**：不論 `editor_mode` 為何，graph-mode profile 跑的都是攤平後的 fallback prompt。本 change 認領 graph 的真正 runtime 執行語意——這是 2026-06-10 eng review 中被點名的責任真空。

關鍵約束（沿用既有架構，不可破壞）：
- **對話策略壞掉不可 fail loud**：SIP 來電以 `AGENT_PROFILE` secret 綁死 profile、無任何 UI banner。graph 無效時必須無聲 fallback 到 `instructions`，來電者不該聽到斷線。
- **realtime 下 graph 執行今天是 broken，不是 slow**：SDK handoff 會對 live 連線呼叫 `update_instructions`（`agent_activity.py:643`），但 Gemini Live 把 instructions 綁在連線建立時。預設 `gemini-2.5-flash-native-audio`（`providers.py:163`）走 mid-session `send_client_content`，第一個 model turn 後遭 **1007 拒絕**（CLAUDE.md 已記載）；`gemini-3.1-flash-live-preview` 則**靜默忽略**新 instructions（`realtime_api.py:550-554`），node prompt 到不了模型。故 v1 graph 僅限 pipeline，且 graph 與 realtime 在 config 層**互斥**（見 D4）。
- **前端 validator 可被繞過**：`frontend/lib/agent-graph.ts` 的 `validateGraph` 只是 UX 提示；直接打 API 寫 config 可繞過。runtime gate 需要後端自己的真相來源。

## Goals / Non-Goals

**Goals:**
- 在 LiveKit Agents runtime 上執行 graph：每個 node 一個 Agent instance，edge 轉移以 SDK 原生 handoff 實現。
- 後端 Python graph validator，規則集與前端 `validateGraph` 對齊，作為「runtime gate」與「API 存檔硬驗證」的唯一真相。
- 策略來源 gate：`editor_mode === 'graph'` 且通過後端 validator → graph 執行；否則 fallback 到 `instructions` + warning log。
- 全域能力（QA inline、services hours、`global_prompt`）注入 global 層，與 node prompt 組合。
- `handoff` node 啟動 = 呼叫 `transfer_to_human`，node `prompt` 作為 per-handoff greeting。

**Non-Goals:**
- graph 編輯器 UX（`graph-agent-builder` 已完成）。
- 模型 provider 解析（`multi-model-runtime` 已完成）。
- realtime mode 的 graph 執行——realtime 下 node 換 instructions 目前 1007/no-op（見 Context），解鎖為獨立 follow-up change（需先 spike），v1 在 config 層直接阻擋 graph+realtime。
- per-node 模型的**實作**：v1 只留介面（node 宣告 model spec 時呼叫同一組 `build_*`），不保證 v1 落地。
- 資料收集變數（`variable_keys`）：schema v1 刻意不含，留待後續 `schema_version` bump。

## Decisions

### D1：以 SDK 原生 multi-agent handoff 組裝，不自建狀態機（review T4 [Layer 1]）

每個 graph node 對應一個 `livekit.agents.Agent` instance：
- `instructions` = `global_prompt`（含 QA/hours 注入）+ node `prompt`（focused）。
- `tools` = node `tools` 解析自 profile 的 tool namespace（同 `agent_factory` 的三層掛載規則）+ 自動生成的**轉移工具**。
- edge 轉移以 SDK 的 function-tool-returns-Agent handoff 機制實現：tool 回傳目標 node 的 Agent instance，SDK 觸發其 `on_enter`。

**為何不自建 FSM**：LiveKit Agents 已提供 multi-agent handoff（含 chat context 傳遞、`on_enter`/`on_exit` 生命週期、tool 註冊）。自建狀態機等於重寫 SDK 已驗證的 turn-taking 與 context 管理，且要自己處理 barge-in、preemptive generation 等邊角。代價是「轉移由 LLM 呼叫工具觸發」而非確定性跳轉——但這對 `user_turn` 邊正是想要的語意（NL 條件由 LLM 評估）。

**替代方案**：自建 graph interpreter（維護 current_node、每回合重設 `session` 的 instructions/tools）。否決：要 hack SDK 內部的 agent activity 換手，且破壞 SDK 對 context 的假設。

### D2：edge 觸發的兩種實現

- **`trigger: user_turn`**：source node 的每條出邊生成一個 handoff function_tool，docstring = 該邊的 `condition`（「當 {condition} 時呼叫」）；空 `condition` = 無條件邊，反映在 instructions 的轉移指示中。LLM 在使用者回合後依 NL 條件決定是否呼叫 → 回傳 target Agent。多邊命中由 `edges` 陣列順序決定優先（工具以該順序生成、instructions 以該順序列出）。
- **`trigger: tool_result`**：電梯案例「建單後立即轉接」需要在 domain tool 回傳後**不等使用者回合**就轉移。SDK 已支援 domain tool **直接回傳 target Agent** 觸發 handoff（`generation.py:767/793`），不需自建額外 dispatcher。v1 語意收斂為**無條件**：node 的 domain tool 完成後即 handoff 到 tool_result 邊的 target（多邊依陣列順序）。
  - **v1 明確不支援非空 `condition` 的 tool_result 邊**（修正 review 後決議）：schema 沒有 tool↔edge 綁定欄位（連「哪個 tool 的哪個結果」都表達不出來）、零驗證案例、且「對 tool 回傳文字做 NL 判定」會在最延遲敏感的 post-tool / pre-handoff 點插入非確定性 LLM 分支——config 作者以為確定性、實得 flaky。改為**顯式契約**：validator 對「tool_result + 非空 condition」發 warning（存檔時），runtime 一律當無條件 + log。真案例出現再 `schema_version` bump 加結構化綁定。

### D3：後端 Python validator 是 runtime gate 與存檔硬驗證的唯一真相（review D2）

新增 `agents/runtime/graph.py` 的 `validate_graph(graph, available_tools, config_tool_names, *, handoff_enabled)`，規則集對齊前端 `validateGraph`：
- errors：唯一 start、node id/edge id 不重複、合法 node type、edge 端點存在、no edge into start、no edge out of end、合法 trigger、從 start 可達性（BFS）。
- warnings：self-loop、多條無條件同源同 trigger 出邊、dangling tool、handoff node 但 handoff 未啟用。

兩個掛載點：
1. **runtime gate**（`entrypoint` / factory）：`editor_mode == 'graph'` 且 `validate_graph().valid` 且 effective mode 為 `pipeline` → 走 graph 執行；否則 fallback。
2. **API 存檔硬驗證**（`routes_profiles.py` 的 create/update）：config 帶 `editor_mode: graph` 時，存檔前跑同一 validator，有 blocking error 回 422。

validator 先做的**真正理由是「它是 gate 的共同依賴」**——executor 的 gate 沒有它寫不出來，順序因此無論如何都對。不是「堵直接打 API 的洞」：在 executor 上線前，透過 API 寫進來的 invalid graph 只會被攤平成無害 instructions、不會被任何東西執行，那個「洞」沒有可利用面。422 的價值與 executor 同時出現。

此 validator 額外承載一條 **mode 耦合**規則（見 D4）：`editor_mode: graph` + `models.mode: realtime` 視為 blocking error（422）。前端 `validateGraph` 維持 UX 提示角色，不移除。

### D4：graph 與 realtime 互斥（mode 耦合）+ 策略來源 gate 與 fallback（review D2、graph-agent-schema「Runtime execution boundary」）

graph 執行僅 pipeline，且這是**完整生產路徑**——profile 設 `models.mode: pipeline` 即可部署上 SIP，不是 demo-only。realtime 下 graph 執行今天 broken（見 Context），故 graph 與 realtime 在 config 層互斥，分兩層落實：

- **save-time 阻擋（主機制）**：validator 對 `editor_mode: graph` + `models.mode: realtime` 發 blocking error → API 422；前端在 graph mode 顯示「需 pipeline 部署」提示（agent mode 在 profile 編輯器不可改，由部署 env 決定）。此組合根本選不出來，是顯式契約而非靜默降級。
- **runtime 兜底（仍須保留）**：deployment 級 `AGENT_MODE=realtime` env 優先於 profile（CLAUDE.md），仍可能讓 graph profile 落到 realtime。此誤配 edge case 降級跑攤平 `instructions` + 大聲 warning。**為何不掛電話**：`ctx.delete_room()` 技術上能掛斷 SIP，但既有 policy（CLAUDE.md / graph-agent-schema）明定「對話策略壞掉不 fail loud」——SIP profile 由 secret 綁死、無任何 UI banner，掛斷 = 來電者被秒掛、零信號的靜默生產事故。寧可降級講完。

`create_agent_class` 分流：
```
editor_mode == 'graph' AND validate_graph().valid AND effective_mode == 'pipeline'
  → 組裝 graph（多 Agent + handoff）
否則
  → 現有單一 instructions 路徑（attach warning log 說明 fallback 原因）
```
fallback 原因要 log 清楚（非 graph mode / validator 失敗 / realtime mode 誤配），但**一律不 raise**。`instructions` 由 graph-agent-builder 每次存檔自動重生，永不過期，是唯一安全網。

### D5：全域能力注入維持 global 層（review、schema 既有約定）

QA inline block、services hours block、`global_prompt` 組成「global preamble」，**前置**到每個 node 的 instructions，不下沉到個別 node。`lookup_qa`（qa_mode == tool）依舊全域自動掛載到每個 node。`transfer_to_human` **不**無條件全域掛載——只在 `handoff` node 啟動時呼叫（node prompt 作 greeting）。

### D6：per-node 模型只留介面（multi-model OQ4）

node 若宣告 model spec，組裝該 node Agent 時呼叫 `agents/runtime/providers.py` 同一組 `build_*`；cost 依 session row 可擴充模型名結構（multi-model task 2.5a）分段記錄。v1 可只保留呼叫點與 fallback 到 session-level 模型，不保證完整落地。

## Risks / Trade-offs

- **[tool_result 與 schema 無 tool↔edge 綁定]** → schema 沒有「哪個 tool 觸發哪條 tool_result 邊」的欄位。v1 收斂為「domain tool 回傳後無條件轉移」、非空 condition 不支援（validator warning）；多 domain tool + 條件式 tool_result 的精準綁定列為 Open Question，必要時以 `schema_version` bump 加欄位。
- **[LLM 不呼叫轉移工具 → 卡在 node]** → user_turn 轉移仰賴 LLM 判斷。緩解：instructions 明列轉移規則與條件；無條件邊在 prompt 中強指示。殘餘風險接受（與 prompt-mode 對話跑飛的風險同級）。
- **[多 Agent 切換的 stale-instruction bleed]** → 每次 handoff SDK 預設帶完整 history。真正的失效模式**不是 token 膨脹**（電話對話幾分鐘、token 自然有界、成本非問題），而是 focused 的下游 node 收到完整 history 後，LLM 仍受上一個 node 指示污染、繼續做舊階段的事或重答已結束話題。v1 用 SDK 預設行為；observability 要觀測的是「轉移後 LLM 是否仍被舊 node 指示污染」，而非 token 曲線。裁剪策略待真實長對話資料後再議（盲調截斷可能砍掉下游 node 合法需要的上文）。
- **[後端/前端 validator 規則漂移]** → 兩套 validator 同規則但不同語言，易 drift。緩解：兩邊以同一份「規則清單」為準（spec 的 scenario），各自配對等測試；改規則時兩邊一起改列入 review checklist。
- **[realtime profile 仍以 fallback 跑]** → graph-mode profile 在 realtime 下跑攤平 instructions，使用者可能誤以為 graph 生效。緩解：runtime warning log 明示；前端 graph mode 顯示「需 pipeline 部署」提示（agent mode 不可在編輯器改，故無法在存檔時硬擋此誤配，僅後端對顯式 `models.mode: realtime` 回 422）。

## Migration Plan

- 純加法：不動 DB schema（config 是 free-form JSON）、不改既有單一 instructions 路徑。graph 執行只在 `editor_mode == 'graph'` 且 pipeline 且 validator 通過時啟用。
- 上線後既有 prompt-mode profile 行為完全不變（gate 預設 `prompt`）。
- rollback：移除 gate 分支即回到「全部走 fallback instructions」，無資料遷移負擔。
- 建置順序：先上後端 validator + API 硬驗證（它是 gate 的共同依賴，且 graph+realtime 互斥的 422 立即有 UX 價值），再上 graph 執行組裝。

## Open Questions

- **tool_result 邊的條件式綁定**：v1 只支援無條件 tool_result。是否需要在 schema 加 `on_tool`/結構化 tool result 來表達「哪個 tool 的哪個結果觸發哪條邊」？留待電梯以外的真實案例出現再定（屆時 `schema_version` bump）。
- **realtime graph 執行（獨立 follow-up change）**：realtime 下 node 換 instructions 目前 1007（native-audio）/no-op（flash-live），不只是延遲未知而是 broken。需獨立 spike 驗證「重建連線 vs. 換 instructions」的可行性與延遲，本 change 在 config 層直接阻擋 graph+realtime、不承諾。
- **stale-instruction bleed 的裁剪策略**：是否在 handoff 時截斷/摘要 history 以避免舊 node 指示污染下游，等真實長對話 observability 後再定。
