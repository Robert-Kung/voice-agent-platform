## Why

現行 Profile Editor v2 把整個對話策略壓進**單一巨型 `instructions` 字串**。電梯維修 agent 的真實 prompt 已經塞進「緊急 / 一般報修 / 非報修」三條分支 + 工具規則 + 分類原則，所有情境互相干擾、難維護、難測試，且 prompt 一長 LLM 越容易漏判分支。我們實測把 elevator agent 拆成 `start →{緊急, 一般, 非報修}→ 轉接/結束` 的 graph 後，每個節點的 prompt 短而專注，邊界清晰、好驗證——這正是 Dograh / Pathors 這類 visual workflow builder 的核心價值。

本提案把設計時體驗從「prompt-first 單欄編輯」演進成 **graph / node-based 對話設計器**：在 canvas 上擺 node、用自然語言 condition 連 edge，每個 node 自帶 focused prompt 與工具。重點在**設計時 UX + 資料模型**；graph 在 runtime 如何被執行（SDK handoff 組裝、每回合 edge 評估）由 **`graph-runtime-executor`** change 負責（2026-06-10 eng review 定案新開——原指向 `multi-model-runtime`，但該提案 scope 為模型解析、從未認領 graph 執行，為責任真空），本提案不碰。graph 執行 v1 限 pipeline mode（realtime 可行性待 executor spike）。

## What Changes

- 新增 **graph 編輯模式**：把現有唯讀的 `agent-flow-builder.tsx`（React Flow hub-and-spoke 視覺化）升級為**可編輯的對話流程 canvas**——可新增 / 刪除 / 連接 node，edge 帶自然語言 condition，點 node 開側欄編 per-node prompt / tools / variables。
- Profile config 新增可選的 **`graph` 區塊**（`schema_version` + `nodes` + `edges` + `global_prompt`），效仿 Pathors/Dograh 的 `workflow_definition`。edge 帶 `trigger`（`user_turn` | `tool_result`，後者表達電梯案例的「工具回傳後立即轉接」）與自然語言 `condition`。前端 graph 編輯器與既有表單讀寫同一份 profile config，**非破壞性**：未宣告 `graph` 的舊 profile 照常以單一 `instructions` 運作。
- **雙模式共存 + 漸進遷移**：profile 有 `editor_mode`（`prompt` | `graph`）旗標——它是 runtime 策略來源的**唯一開關**（`editor_mode === 'graph'` 且驗證通過才走 graph，否則 instructions fallback），不只是視圖偏好，模式切換後的存檔需 confirm。提供「轉成 graph」動作把既有單一 `instructions` profile 視為單節點 graph（一個 `start` node 持有原 `instructions`，工具掛上去）；graph 模式下每次存檔以 `graphToPrompt` 自動重生 `instructions` fallback，確保 executor 落地前（含 SIP 場景）的降級執行永不過期。
- **Node 類型**：`start`（入口，必有且唯一）、`prompt`（情境節點，帶 focused prompt + tools + variables）、`end`（終止）、`handoff`（轉真人，包現有 `human_operator` 設定）。沿用既有 React Flow 與設計 token，不引入新視覺體系。
- **既有右側折疊面板**（QA / Hours / Identity / Advanced）保留為 **graph-level 全域設定**；Tools 與 Handoff 的編輯從全域下沉成可掛在特定 node 的能力，但既有全域 tools 仍相容（視為掛在 start node）。
- AI Generate 既有的 create / enhance 能力擴充出可選的 **graph 草稿生成**（描述 → nodes+edges JSON 初稿），沿用現有 `/api/admin/generate-prompt` 模式，不在本提案強制實作（標為延伸）。

## Capabilities

### New Capabilities
- `graph-agent-schema`: profile config 的 graph 資料模型——`graph.schema_version` / `graph.nodes` / `graph.edges` / `graph.global_prompt` 欄位定義、node 類型與欄位（`id` / `type` / `title` / `prompt` / `tools` / `position`）、edge 欄位（`id` / `source` / `target` / `trigger` / `condition` / `label`）、`editor_mode` 作為策略來源唯一開關的契約、fallback `instructions` 自動重生（`graphToPrompt`）、單一 `instructions` profile 視為單節點 graph 的等價映射。
- `graph-editor-ux`: 設計時的 graph 編輯器互動——canvas 上 node 增刪連線（controlled、語意事件上拋）、edge trigger/condition 編輯、node 側欄（per-node prompt / tools；start node 投影 welcome 欄位）、`prompt` 與 `graph` 雙編輯模式切換（含 confirm）與漸進遷移流程、graph 結構驗證提示（唯一 start、可達性、進出邊規則、工具合法名單）、與既有右側全域設定面板的整合。

### Modified Capabilities
<!-- openspec/specs/ 目前為空，無既有已歸檔 capability 可改；全部列為新增。 -->

## Impact

- **Frontend（主要）**：
  - `frontend/components/admin/agent-flow-builder.tsx`——從唯讀 hub-and-spoke 升級為可編輯對話 graph（新 node 類型、edge condition 編輯、connect handlers）。
  - 新增 node 側欄編輯元件（per-node prompt / tools / variables），可複用既有 `tools-section.tsx`。
  - `frontend/hooks/use-profile-form.ts`——`KnownConfig` 加 `graph` 與 `editor_mode`；新增 graph 增刪節點 / 邊 / node 欄位的 actions；`buildConfig` / `splitConfig` 納入 `graph`；單 prompt → 單節點 graph 的遷移 helper。
  - `frontend/app/admin/(authenticated)/profiles/[id]/page.tsx`——依 `editor_mode` 切換 prompt-first 與 graph canvas 兩種中央編輯區；`buildFlowFromConfig` 改讀 `graph` 區塊（無 graph 時 fallback 現行 config 推導）。
- **資料模型 / API**：profile `config` 為 free-form `dict[str, Any]`（見 `agents/db/models.py` `config_json`、`agents/api/schemas.py`），**新增 `graph` 不需 DB migration**；`agents/api/routes_profiles.py` 驗證若要對 graph 結構把關需擴充（可選，本提案先以前端驗證為主）。
- **Profiles**：`agents/profiles/*.yaml` 可選 `graph` 區塊；提供 `elevator_repair` 的 graph 版本作為參考範例（與既有 `instructions` 版並存或替換）。
- **共享邊界**：三個 change 分工——本提案負責設計時 + 資料模型；`multi-model-runtime` 負責模型解析；**graph 的 runtime 執行（SDK handoff 組裝、edge 觸發評估、節點切換、後端 Python validator）由 `graph-runtime-executor` change 負責**。`graph` 資料模型（含 `schema_version`）是三者間的凍結契約。
- **Out of scope**：graph runtime 執行語意、後端 graph validator（executor 認領）、edge 條件的 LLM 評估、graph 版 cost 計費、`variable_keys` 資料蒐集變數（自 v1 schema 移除，待 executor 定義語意後加回）、AI 自動生成 graph 的強制實作。
