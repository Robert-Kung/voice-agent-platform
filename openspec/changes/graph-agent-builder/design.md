## Context

Profile Editor v2 (現為 default editor，路徑 `frontend/app/admin/(authenticated)/profiles/[id]/page.tsx`，v2 路由已 redirect 至此) 是 split-panel、prompt-first 架構：中央 CodeMirror 編 `instructions` 單一字串，右側折疊面板編 Tools / QA / Hours / Handoff / Identity / Advanced。右側面板頂部已有一個 **唯讀** 的 React Flow 視覺化 (`agent-flow-builder.tsx`)，用 hub-and-spoke 佈局把 instructions / qa / hours / handoff / tools 當 spoke 連到中央 "Agent core"——它只是把現有 config **投影**成圖，不能編輯、也沒有對話流程語意。

現況資料模型（`use-profile-form.ts` 的 `KnownConfig` + `agents/profiles/*.yaml`）：對話策略 100% 在單一 `instructions` 字串，`tools` 是 profile 層的扁平陣列，`human_operator` 是全域 handoff 設定。profile `config` 在 DB 是 free-form JSON（`config_json` Text 欄位）、API schema 是 `dict[str, Any]`，所以**加欄位不需 migration**。

動機（見 proposal）：單一巨型 prompt 把多情境揉在一起，難維護難測。實測把 elevator agent 拆成 `start →{緊急, 一般報修, 非報修}→ handoff/end` 的 graph 後乾淨許多。本設計把設計時體驗演進成 graph-based，效仿 Pathors / Dograh 的 `workflow_definition`（nodes + edges + global prompt，前端用 React Flow，visual builder 與 API 讀寫同一份 JSON）。

關鍵約束：runtime 如何**執行** graph 不在本提案——由 `multi-model-runtime` 提案負責（該提案 proposal 已明文把 graph UX/資料模型反向 defer 給本提案，邊界互斥乾淨）。本提案產出的 `graph` 資料模型是兩個提案的契約介面。

## Goals / Non-Goals

**Goals:**
- 定義 profile config 的 `graph` 區塊資料模型（nodes / edges / global_prompt），結構與 Pathors/Dograh 對齊、可被前端編輯器與未來 runtime 共讀。
- 把唯讀的 `agent-flow-builder.tsx` 升級成可編輯對話 canvas：node 增刪、edge 連線 + 自然語言 condition、node 側欄編 per-node prompt / tools / variables。
- `prompt` 與 `graph` 兩種編輯模式共存；提供既有單 prompt profile **無損**轉成單節點 graph 的漸進遷移路徑。
- 100% 非破壞性：未宣告 `graph` 的舊 profile 行為不變。

**Non-Goals:**
- Graph 的 runtime 執行語意（狀態機、每回合 edge 條件評估、節點轉移、global prompt 如何疊加進每個 LLM call）——`multi-model-runtime` 負責。
- Graph 版的 cost 計費、多模型節點。
- AI 自動生成 graph（描述 → nodes+edges）強制實作——列為延伸，本提案只預留 UX 入口。
- 後端對 graph 結構的硬性 schema 驗證（先以前端驗證為主，後端驗證列為可選）。
- Mobile (<640px) 響應式 graph 編輯（沿用 v2「桌面為主」決定）。

## Decisions

### D1. `graph` 作為 profile config 的可選並列區塊，而非取代 `instructions`

`config.graph = { global_prompt, nodes[], edges[] }`，與既有 `instructions` / `tools` / `human_operator` 並存。`editor_mode: 'prompt' | 'graph'` 旗標決定編輯器預設開哪個視圖。

- **為何不直接用 `instructions` 存 graph JSON**：`instructions` 是給 LLM 的字串，graph 是結構化資料，混存會破壞既有 runtime 與 prompt-first 編輯。
- **相容優先序（契約給 runtime 用）**：runtime 看 `editor_mode` / `graph` 是否存在——有 graph 走 graph，否則走既有單 `instructions`。`global_prompt` 概念上對應「跨所有節點的共用 prompt」，遷移時可由原 `instructions` 充當。
- **Alternative considered**：另開一張 DB table 存 graph。否決——`config_json` 已是 free-form JSON，加 table 增加 migration 與兩處真相不同步風險，違背「profile config 單一真相」。

### D2. Node 類型收斂為 4 種：`start` / `prompt` / `end` / `handoff`

對齊 Pathors 的 `start | prompt | goto` 但落地到本專案語意：

| type | 語意 | 對應既有概念 |
|------|------|--------------|
| `start` | 唯一入口節點，承載 welcome 與初始 prompt | welcome_message / welcome_instructions + 首段 instructions |
| `prompt` | 情境節點，focused prompt + 可掛 tools + variable_keys | instructions 內的某條分支 |
| `handoff` | 轉真人 | 既有 `human_operator` 設定 |
| `end` | 對話終止 | （隱式）通話結束 |

- Pathors 的 `goto` 是「無條件跳轉」，本設計用 **edge condition 為空字串** 表達無條件轉移，不另設 node 類型——少一種 node、edge 語意更一致。
- QA / Service Hours **不做成 node**：它們是橫切全域能力（lookup / 營業判斷），保留在右側全域面板當 graph-level 設定，避免 node 類型爆炸。這也保住既有 `qa-section` / `hours-section` 元件原樣複用。

### D3. Node / Edge 欄位形狀（與 React Flow 對齊）

```jsonc
// config.graph
{
  "global_prompt": "跨所有節點共用的角色 / 語氣 / 鐵則",
  "nodes": [
    {
      "id": "start",                 // 穩定字串 id，前端產生（nanoid）
      "type": "start",               // start | prompt | end | handoff
      "title": "接聽",                // 顯示名稱
      "prompt": "向來電者打招呼…",     // 此節點 focused prompt（end 可空）
      "tools": ["create_maintenance_ticket"], // 掛在此節點的工具 name 陣列（指向 profile.tools / builtin）
      "variable_keys": ["building_name", "elevator_id"], // 此節點期望蒐集 / 使用的變數
      "position": { "x": 0, "y": 0 } // React Flow 畫布座標，純 UI
    }
  ],
  "edges": [
    {
      "id": "e1",
      "source": "start",
      "target": "emergency",
      "condition": "來電者描述關人 / 受傷 / 冒煙等緊急狀況", // 自然語言；空字串=無條件
      "label": "緊急"                // 畫布上顯示的短標籤，可選
    }
  ]
}
```

- `tools` 用既有的工具 `name`（與 `KnownConfig.tools[].name` 同一命名空間），node 只是「引用」工具不重新定義；工具的 HTTP 設定 / parameters 仍由既有 `tools-section` 在全域 tools 清單維護。**為何不在 node 內嵌完整 tool 定義**：避免同一工具在多 node 重複定義 / 走樣，保持工具單一真相。
- `position` 是純 UI 座標，存進 config 讓畫布佈局可持久（Dograh / React Flow 慣例）。
- `condition` 是自然語言字串（runtime 未來用 LLM 評估），設計時只當文字編輯，**本提案不評估其語意**。

### D4. 遷移：單 `instructions` profile = 單節點 graph（無損、可逆）

「轉成 graph」動作 (`promptToGraph` helper)：
1. 建一個 `start` node，`prompt = 原 instructions`，`tools = 原 profile.tools 的 name`，`title = '主流程'`。
2. 若 `human_operator.enabled`，加一個 `handoff` node + 一條 `condition: '需要轉接真人'` 的 edge。
3. 設 `editor_mode = 'graph'`，**保留原 `instructions` 不刪**（作為 fallback / 可逆回 prompt 模式）。

反向（graph → prompt）：切回 `editor_mode = 'prompt'` 即用回 `instructions`；本提案不自動把 graph 攤平回 `instructions`（攤平語意屬 runtime / 生成範疇，列 open question）。

- **為何保留原 `instructions`**：可逆、非破壞、降低使用者抗拒。代價是 graph 模式下 `instructions` 可能與 graph 不同步——以 `editor_mode` 為準解決（UI 明示「目前由 graph 驅動」）。

### D5. 編輯器整合：中央區依 `editor_mode` 切換，右側全域面板保留

- 中央 60% 區：`editor_mode='prompt'` → 現有 `PromptEditor`（CodeMirror）；`='graph'` → 可編輯的 `AgentFlowBuilder` canvas（去掉 `readOnly`，加 node palette / connect / 刪除）。
- 點選 node → 右側面板切成 **Node Inspector**（per-node title / prompt / tools / variable_keys）；未選 node → 顯示既有全域面板（QA / Hours / Identity / Advanced + `global_prompt` 編輯）。Tools 與 Handoff 從純全域變成「可在 node 層引用」，但全域 tools 清單仍是工具定義來源。
- `buildFlowFromConfig` 改成：有 `config.graph` → 直接渲染 graph；無 → 維持現行從 config 推導的唯讀投影（向後相容，舊 profile 列表縮圖仍可用）。

- **Alternative considered**：另開 `/v3` 路由做 graph 編輯器、不動現有頁。否決——v2 路由剛被 retire/redirect（見近期 commit），再開平行路由會重蹈 v1/v2 並存的維護債；用 `editor_mode` 在同一頁切視圖更乾淨。

### D6. Graph 結構驗證放前端（後端驗證可選）

前端在 save 前驗證並提示（非阻擋性 warning + 阻擋性 error 分級）：
- error：無 `start` node、多個 `start`、node id 重複。
- warning：孤立節點（無 in/out edge）、edge `condition` 為空但 source 有多條出邊（歧義）、引用了不存在的 tool name。

後端 `routes_profiles.py` 維持 free-form dict（與 `multi-model-runtime` 一致的決定），graph 結構驗證列為**可選後續**，避免兩提案同時改後端 schema 互相踩到。

## Risks / Trade-offs

- **[graph 與 `instructions` 不同步]** → 以 `editor_mode` 為唯一真相，UI 明示當前驅動來源；遷移保留原 `instructions` 確保可逆。
- **[node `tools` 引用的工具被全域刪除 → 懸空引用]** → 前端 save 前 warning 列出懸空引用；不自動刪 node 內引用（避免悄悄改變設計意圖）。
- **[runtime 尚未支援 graph，使用者建了 graph 卻無法 Try]** → 本提案在 graph 模式的 Try / deploy 行為依賴 `multi-model-runtime`；在 runtime 落地前，graph 模式 profile 的「Try」應降級（明示 runtime 未支援 / 仍跑 `instructions` fallback）。需與 runtime 提案協調上線順序——列 open question。
- **[node 數量多時 canvas 認知負擔]** → 沿用 React Flow 內建 Controls / fit-view / minimap；node 用既有 chart-N 色票區分類型；本提案不做自動佈局（保留手動 position）。
- **[既有 147 個測試]** → 本提案主要動 frontend + profile config 形狀；`agents/tests/test_agent_system.py` 對既有 profile 的 assertion 不應因「新增可選 graph 區塊」而改變（舊 profile 不帶 graph）。新增 elevator graph 範例 profile 若改動既有 `elevator_repair.yaml` 的 assertion 需同步。

## Migration Plan

1. 加 `graph` / `editor_mode` 型別與 hook actions（純加法，預設不影響舊 profile）。
2. 升級 `agent-flow-builder.tsx` 為可編輯；中央區依 `editor_mode` 切換。
3. 提供「轉成 graph」按鈕（`promptToGraph`），讓使用者逐一試遷移。
4. 產出 `elevator_repair` 的 graph 範例（新檔或並列欄位）作為 dogfood + 文件範例。
5. Rollback：`graph` 是可選欄位，移除前端 graph 模式入口即回到純 prompt-first，舊 profile 無感。

## Open Questions

1. **Graph 模式 profile 的 Try / deploy 行為**：runtime 尚未支援 graph 執行前，graph profile 的 Try 應該（a）擋下並提示 runtime 未支援，還是（b）以保留的 `instructions` fallback 執行？需與 `multi-model-runtime` 協調上線順序。
2. **`global_prompt` 與遷移保留的 `instructions` 關係**：遷移時 `global_prompt` 是否應自動填入原 `instructions` 的「鐵則 / 角色」段落，還是留空讓使用者手動拆？目前傾向留空 + 提示，避免亂猜切分。
3. **graph → prompt 攤平**：是否需要把 graph 自動攤平回單一 `instructions`（給不支援 graph 的部署路徑 / SIP fallback 用）？此屬生成 / runtime 範疇，傾向交給 runtime 提案，本提案先不做。
4. **node 內 variable_keys 與 HTTP tool parameters 的關係**：`variable_keys` 是否應與工具 parameter 名稱對齊 / 自動連動？本提案先當自由文字陣列，連動列後續。
5. **AI 生成 graph**：是否在本提案就做 `/api/admin/generate-prompt` 的 graph 模式（輸出 nodes+edges JSON）？目前列延伸、僅預留 UX 入口。
