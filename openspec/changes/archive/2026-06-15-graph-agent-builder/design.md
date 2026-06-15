## Context

Profile Editor v2 (現為 default editor，路徑 `frontend/app/admin/(authenticated)/profiles/[id]/page.tsx`，v2 路由已 redirect 至此) 是 split-panel、prompt-first 架構：中央 CodeMirror 編 `instructions` 單一字串，右側折疊面板編 Tools / QA / Hours / Handoff / Identity / Advanced。右側面板頂部已有一個 **唯讀** 的 React Flow 視覺化 (`agent-flow-builder.tsx`)，用 hub-and-spoke 佈局把 instructions / qa / hours / handoff / tools 當 spoke 連到中央 "Agent core"——它只是把現有 config **投影**成圖，不能編輯、也沒有對話流程語意。

現況資料模型（`use-profile-form.ts` 的 `KnownConfig` + `agents/profiles/*.yaml`）：對話策略 100% 在單一 `instructions` 字串，`tools` 是 profile 層的扁平陣列，`human_operator` 是全域 handoff 設定。profile `config` 在 DB 是 free-form JSON（`config_json` Text 欄位）、API schema 是 `dict[str, Any]`，所以**加欄位不需 migration**。

動機（見 proposal）：單一巨型 prompt 把多情境揉在一起，難維護難測。實測把 elevator agent 拆成 `start →{緊急, 一般報修, 非報修}→ handoff/end` 的 graph 後乾淨許多。本設計把設計時體驗演進成 graph-based，效仿 Pathors / Dograh 的 `workflow_definition`（nodes + edges + global prompt，前端用 React Flow，visual builder 與 API 讀寫同一份 JSON）。

關鍵約束：runtime 如何**執行** graph 不在本提案——由 **`graph-runtime-executor`** change 負責（2026-06-10 eng review 定案新開，因 `multi-model-runtime` 的 scope 為模型解析、從未認領 graph 執行）。本提案產出的 `graph` 資料模型是三個 change 的契約介面。

## Goals / Non-Goals

**Goals:**
- 定義 profile config 的 `graph` 區塊資料模型（schema_version / global_prompt / nodes / edges），結構與 Pathors/Dograh 對齊、可被前端編輯器與 `graph-runtime-executor` 共讀。
- 把唯讀的 `agent-flow-builder.tsx` 升級成可編輯對話 canvas：node 增刪、edge 連線 + 自然語言 condition + trigger、node 側欄編 per-node prompt / tools。
- `prompt` 與 `graph` 兩種編輯模式共存；提供既有單 prompt profile 轉成單節點 graph 的漸進遷移路徑，且 fallback `instructions` 由 graph 自動重生、永不過期。
- 100% 非破壞性：未宣告 `graph` 的舊 profile 行為不變。

**Non-Goals:**
- Graph 的 runtime 執行語意（SDK handoff 組裝、edge 觸發評估、節點轉移、global prompt 如何疊加進每個 LLM call）——`graph-runtime-executor` 負責。
- Graph 版的 cost 計費、多模型節點（`multi-model-runtime` OQ4 / executor 介面點）。
- AI 自動生成 graph（描述 → nodes+edges）強制實作——列為延伸，本提案只預留 UX 入口。
- 後端對 graph 結構的硬性 schema 驗證——**由 `graph-runtime-executor` 認領**（Python validator 為 runtime gate 的唯一真相，存檔 API 亦掛同一 validator）；本提案的前端 `validateGraph` 僅為 UX 即時提示。
- Mobile (<640px) 響應式 graph 編輯（沿用 v2「桌面為主」決定）。

## Decisions

> 標註「review 定案」者為 2026-06-10 plan-eng-review（含 outside voice）的決議。

### D1. `graph` 作為 profile config 的可選並列區塊，而非取代 `instructions`

`config.graph = { schema_version, global_prompt, nodes[], edges[] }`，與既有 `instructions` / `tools` / `human_operator` 並存。`editor_mode: 'prompt' | 'graph'` 旗標決定編輯器預設開哪個視圖。

- **為何不直接用 `instructions` 存 graph JSON**：`instructions` 是給 LLM 的字串，graph 是結構化資料，混存會破壞既有 runtime 與 prompt-first 編輯。
- **策略來源契約（review 定案，給 runtime 用）**：`editor_mode === 'graph'` **且 graph 通過結構驗證** → 執行 graph；其餘情況（`editor_mode` 缺省或 `'prompt'`、graph 區塊缺失、驗證不過）一律執行 `instructions` 並記 log warning。`editor_mode` 是唯一開關，graph 區塊的存在與否**不是**判斷依據（轉換後切回 prompt 模式時 graph 仍保留但不生效）。對話策略壞掉不 fail loud——模型壞了有 FallbackAdapter 接，策略壞了唯一的網是 instructions，懲罰不該落在來電者身上。
- **`schema_version: 1`（review 定案）**：三個 change 共用、存進客戶 DB 的契約必須帶版本欄位；未來 schema 演進靠它判別，不靠啟發式遷移。
- **Alternative considered**：另開一張 DB table 存 graph。否決——`config_json` 已是 free-form JSON，加 table 增加 migration 與兩處真相不同步風險，違背「profile config 單一真相」。

### D2. Node 類型收斂為 4 種：`start` / `prompt` / `end` / `handoff`

對齊 Pathors 的 `start | prompt | goto` 但落地到本專案語意：

| type | 語意 | 對應既有概念 |
|------|------|--------------|
| `start` | 唯一入口節點，承載 welcome 與初始 prompt | welcome_message / welcome_instructions + 首段 instructions |
| `prompt` | 情境節點，focused prompt + 可掛 tools | instructions 內的某條分支 |
| `handoff` | 轉真人 | 既有 `human_operator` 設定 |
| `end` | 對話終止 | （隱式）通話結束 |

- Pathors 的 `goto` 是「無條件跳轉」，本設計用 **edge condition 為空字串** 表達無條件轉移，不另設 node 類型——少一種 node、edge 語意更一致。
- **handoff 語意（review 定案，契約注記給 executor）**：handoff node 的觸發即 `transfer_to_human` 呼叫；node 的 `prompt` 欄位作為該 handoff 的 per-node greeting/instructions（因此多個 handoff 節點、不同轉接話術可表達）。graph 模式下 `transfer_to_human` 不再因 `human_operator.enabled` 無條件全域掛載——掛載範圍由 executor 依「handoff node 可達性」決定，本提案僅定資料形狀。
- QA / Service Hours **不做成 node**：它們是橫切全域能力（lookup / 營業判斷），保留在右側全域面板當 graph-level 設定，避免 node 類型爆炸。這也保住既有 `qa-section` / `hours-section` 元件原樣複用。**注入點（review 定案）**：QA inline / services 在 graph 模式下併入 global 層（global_prompt 組合），不下沉到 node——寫進 runtime boundary 給 executor。

### D3. Node / Edge 欄位形狀（與 React Flow 對齊）

```jsonc
// config.graph
{
  "schema_version": 1,
  "global_prompt": "跨所有節點共用的角色 / 語氣 / 鐵則",
  "nodes": [
    {
      "id": "start",                 // 穩定字串 id，前端產生（nanoid）
      "type": "start",               // start | prompt | end | handoff
      "title": "接聽",                // 顯示名稱
      "prompt": "向來電者打招呼…",     // 此節點 focused prompt（end 可空；handoff = 轉接話術）
      "tools": ["create_maintenance_ticket"], // 掛在此節點的工具 name 陣列（指向 profile.tools / builtin / auto-mounted）
      "position": { "x": 0, "y": 0 } // React Flow 畫布座標，純 UI
    }
  ],
  "edges": [
    {
      "id": "e1",
      "source": "start",
      "target": "emergency",
      "trigger": "user_turn",        // user_turn | tool_result；缺省 user_turn
      "condition": "來電者描述關人 / 受傷 / 冒煙等緊急狀況", // 自然語言；空字串=無條件
      "label": "緊急"                // 畫布上顯示的短標籤，可選
    }
  ]
}
```

- **`trigger`（review 定案，outside voice P1）**：純 NL condition 表達不了電梯案例自己的核心規則（「工具回傳後立即轉真人」「建單失敗也立即轉真人」）——觸發點是工具結果不是使用者發言。`user_turn`（預設）= 使用者回合後評估 condition；`tool_result` = 節點上工具回傳後依結果轉移。不現在補、之後改 = 遷移已存進客戶 DB 的 graph。
- **多邊命中優先序（review 定案）**：依 `edges` 陣列順序取第一個命中者。同一 source 多條無條件出邊因此語意明確（後面的永遠輪不到），驗證降為 warning。
- `tools` 用既有的工具 `name`（與 `KnownConfig.tools[].name` 同一命名空間），node 只是「引用」工具不重新定義；工具的 HTTP 設定 / parameters 仍由既有 `tools-section` 在全域 tools 清單維護。**為何不在 node 內嵌完整 tool 定義**：避免同一工具在多 node 重複定義 / 走樣，保持工具單一真相。
- `position` 是純 UI 座標，存進 config 讓畫布佈局可持久（Dograh / React Flow 慣例）。**已知 trade-off（review 定案，接受）**：拖曳節點會觸發 `is_dirty` / 待部署標記——layout 也是 config 的一部分；為 position 開「不算 dirty」的特例會引入部分欄位例外的複雜度，不值得。
- `condition` 是自然語言字串（runtime 由 executor 用 LLM 評估），設計時只當文字編輯，**本提案不評估其語意**。
- **`variable_keys` 已自 v1 移除（review 定案，outside voice P2）**：零語意欄位是契約負債——executor 之後被迫追認使用者已填的任意字串。資料蒐集變數待 executor 定義語意後隨 `schema_version` bump 加回。

### D4. 遷移：單 `instructions` profile = 單節點 graph；fallback 自動保鮮

「轉成 graph」動作 (`promptToGraph` helper)：
1. 建一個 `start` node，`prompt = 原 instructions`，`tools = 原 profile.tools 的 name`，`title = '主流程'`。
2. 若 `human_operator.enabled`，加一個 `handoff` node + 一條 `condition: '需要轉接真人'` 的 edge。
3. 設 `editor_mode = 'graph'`，原 `instructions` 保留。

**Fallback 自動重生（review 定案，outside voice P1——取代「凍結原文」）**：graph 模式下**每次存檔**以 `graphToPrompt` 攤平函數重生 `instructions`（global_prompt + 各節點 title/prompt + edge trigger/condition 描述的結構化串接）。理由：凍結的 fallback 會過期——使用者轉 graph 後只編輯圖，幾週後 SIP 來電（profile 被 `AGENT_PROFILE` pin 死、無任何 UI banner 可見）拿到的是古董 prompt、零訊號。自動重生讓安全網永遠與 graph 同步，順勢關閉原 OQ3。

反向（graph → prompt）：切回 `editor_mode = 'prompt'` 即用 `instructions`（= 最近一次攤平結果）。**可逆性的誠實標示（review 定案）**：「無損可逆」只在轉換瞬間成立；graph 編輯過後切回 prompt 拿到的是攤平結果而非原文——UI 須明示，不得宣稱 lossless round-trip。

- `promptToGraph` / `graphToPrompt` 為一對對稱純函數，皆上單元測試（見 D7 測試決策）。

### D5. 編輯器整合：中央區依 `editor_mode` 切換，右側全域面板保留

- 中央 60% 區：`editor_mode='prompt'` → 現有 `PromptEditor`（CodeMirror）；`='graph'` → 可編輯的 `AgentFlowBuilder` canvas（去掉 `readOnly`，加 node palette / connect / 刪除）。
- **Canvas 狀態所有權（review 定案）**：`useProfileForm.known.graph` 是唯一真相，canvas 為 **controlled**——nodes/edges 由 `config.graph` derive，變更只在**語意事件**（connect / node・edge 刪除 / drag-stop / Inspector 編輯）時經 callback 流回 hook，不逐 pixel 上拋（避免 `currentSnapshot` stringify 抖動）。現有元件是單向死路（`useNodesState` 只吃一次 props、宣告的 `onNodesChange` props 從未被呼叫），照現狀去掉 readOnly 會 silent data loss——此契約為實作前提，非 UI 細節。既有 `FlowNodeType` 的 `'prompt'`（hub-and-spoke spoke 語意）與新對話節點 `prompt` 同名異義，升級時一併 rename 隔離。
- 點選 node → 右側面板切成 **Node Inspector**（per-node title / prompt / tools；edge 選取時編 trigger / condition / label）；未選 node → 顯示既有全域面板（QA / Hours / Identity / Advanced + `global_prompt` 編輯）。Tools 與 Handoff 從純全域變成「可在 node 層引用」，但全域 tools 清單仍是工具定義來源。
- **welcome 欄位投影（review 定案）**：`welcome_message` / `welcome_instructions` 的編輯 UI 目前只活在 `PromptEditor`（graph 模式下消失，但 runtime 每通電話仍用它們開場）。選取 `start` node 時 Node Inspector 額外顯示這兩欄——資料仍存 top-level config，純 UI 投影、零 schema 變更。
- **Mode 切換 confirm（review 定案）**：`editor_mode` 不只是視圖偏好，存檔後直接改變**線上執行策略**。切換模式後的存檔需 confirm 明示（「此存檔將改變 runtime 執行來源為 graph/prompt」）；切回 prompt 時同時標示「graph 後續編輯不會反映於 prompt 模式」。
- `buildFlowFromConfig` 改成：有 `config.graph` → 直接渲染 graph；無 → 維持現行從 config 推導的唯讀投影（向後相容，舊 profile 列表縮圖仍可用）。

- **Alternative considered**：另開 `/v3` 路由做 graph 編輯器、不動現有頁。否決——v2 路由剛被 retire/redirect（見近期 commit），再開平行路由會重蹈 v1/v2 並存的維護債；用 `editor_mode` 在同一頁切視圖更乾淨。

### D6. Graph 結構驗證：前端做 UX 提示，runtime gate 歸 executor

前端 `validateGraph(graph, availableTools)` 在 save 前驗證並提示（阻擋性 error 與非阻擋性 warning 分級）：

- **error**：無 `start` node、多個 `start`、node id 重複、edge 端點不存在、**從 start 不可達的節點**（review 補強：孤立環會通過單純的孤立節點檢查）、**start 有入邊 / end 有出邊**、trigger 非法值。
- **warning**：同一 source 多條無條件出邊（依 D3 順序優先，後面的永遠輪不到）、引用了不存在的 tool name。
- **工具合法名單（review 定案）**：`config.tools` 名稱 ∪ builtin `availableTools`（toolsApi）∪ `AUTO_MOUNTED_TOOLS`（`lookup_qa` / `transfer_to_human`——`cleanLegacyTools` 會主動把它們清出 config.tools，照字面只查 config.tools 會對 handoff 流程自己誤報）。`availableTools` 載入失敗時跳過此項檢查，不誤報。

**Runtime gate 的唯一真相是後端 Python validator，由 `graph-runtime-executor` 認領（review 定案，outside voice P2）**：前端驗證可被繞過（直接 API 寫入、未來 AI 生成），且 TS/Python 雙實作必然漂移——executor 的 validator 同時掛在「執行前 gate」與「存檔 API 硬驗證」兩處。本提案的前端版定位為即時 UX 提示。

### D7. Runtime 執行歸屬與邊界（review 新增決策）

- **執行器**：`graph-runtime-executor`（新 change，review 定案開立）負責全部執行語意。實作提示（outside voice 挑戰吸收，[Layer 1]）：**不自建狀態機**——LiveKit Agents SDK 原生 multi-agent handoff 即「node = Agent instance、edge = handoff 轉移」，executor 是組裝 SDK 內建而非發明機制。
- **Alternative considered（review 定案記錄）**：放棄 graph、改用「結構化子 prompt + SDK handoff、無視覺編輯器」。否決——本提案的原始目標是**更好的前端 Agent 設計流程**（對標 Dograh / Pathors，非工程師可編輯、流程可視化可驗證），視覺化設計器是目的不只是手段；但 SDK handoff 作為 executor 的實作機制被採納。
- **模式邊界（review 定案）**：graph 執行 v1 **僅支援 pipeline mode**。realtime 的 TextInputRealtimeModel 把 instructions 綁定在 Gemini Live 連線建立時，節點切換 = 重連（延遲尖刺）或每回合額外 LLM 評估（同樣打到延遲命門），可行性未經驗證——列為 executor 提案的 spike / open question，驗證前不承諾。
- 在 executor 落地前，graph 模式 profile 的 Try / deploy 跑 `instructions` fallback（D4 自動重生，永不過期）+ 編輯器 banner 明示「目前由 instructions fallback 執行」。

## Risks / Trade-offs

- **[graph 與 `instructions` 不同步]** → D4 自動重生：graph 模式下 instructions 即 graph 的攤平投影，每次存檔同步。
- **[node `tools` 引用的工具被全域刪除 → 懸空引用]** → 前端 save 前 warning 列出懸空引用；不自動刪 node 內引用（避免悄悄改變設計意圖）。
- **[runtime 尚未支援 graph，使用者建了 graph 卻無法 Try]** → fallback 永不過期（D4）+ banner（D7）；executor 落地順序見 `graph-runtime-executor` change。
- **[攤平品質不如人寫 prompt]** → `graphToPrompt` 是結構化串接、無 LLM 潤飾，可能生硬——但它反映「現在的設計」而非凍結的古董；後續可掛 AI enhance（既有 generate-prompt 基礎）。
- **[node 數量多時 canvas 認知負擔]** → 沿用 React Flow 內建 Controls / fit-view / minimap；node 用既有 chart-N 色票區分類型；本提案不做自動佈局（保留手動 position）。
- **[既有 147 個測試]** → 本提案主要動 frontend + profile config 形狀；`agents/tests/test_agent_system.py` 對既有 profile 的 assertion 不應因「新增可選 graph 區塊」而改變（舊 profile 不帶 graph）。新增 elevator graph 範例 profile 若改動既有 `elevator_repair.yaml` 的 assertion 需同步。

## Migration Plan

1. 加 `graph` / `editor_mode` 型別與 hook actions（純加法，預設不影響舊 profile）；前端建 vitest（純函數測試，見 tasks §7）。
2. 升級 `agent-flow-builder.tsx` 為可編輯（controlled 契約）；中央區依 `editor_mode` 切換。
3. 提供「轉成 graph」按鈕（`promptToGraph`）與存檔自動攤平（`graphToPrompt`），讓使用者逐一試遷移。
4. 產出 `elevator_repair` 的 graph 範例（含 `tool_result` trigger 邊）作為 dogfood + 文件範例。
5. Rollback：`graph` 是可選欄位，移除前端 graph 模式入口即回到純 prompt-first，舊 profile 無感。

## Open Questions

> 原 OQ1（Try 行為）、OQ3（攤平）、OQ4（variable_keys 連動）已於 2026-06-10 review 定案，見 D4 / D7 / D3。

1. **`global_prompt` 與遷移的關係（維持原傾向）**：遷移時 `global_prompt` 留空 + 提示使用者手動把「鐵則 / 角色」段落拆過去，不自動猜切分。
2. **AI 生成 graph**：是否在本提案就做 `/api/admin/generate-prompt` 的 graph 模式（輸出 nodes+edges JSON）？維持列延伸、僅預留 UX 入口。
