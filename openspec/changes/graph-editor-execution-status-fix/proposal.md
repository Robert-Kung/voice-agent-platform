## Why

`graph-runtime-executor` 已 archive（graph 在 pipeline mode 下由 runtime 原生執行），但 Profile Editor 前端有兩處與已上線 runtime 對不上的純 hygiene 缺口，會誤導部署者、且違反前後端 validator parity 原則。這兩項與更大的模型/語音 UI 重設計（`profile-editor-model-voice-ux`）無耦合，獨立、低風險，先單獨 ship，不被 feature 卡住（autoplan CEO review F6）。

## What Changes

- **修正過期執行狀態文案**：`frontend/app/admin/(authenticated)/profiles/[id]/page.tsx` 殘留「graph 執行待 graph-runtime-executor 落地 / Try·部署一律走 instructions fallback」的無條件 banner（中央 ~L124-128）與 SaveConfirmModal（~L297-302）。改為依 profile 宣告 mode 的條件式狀態：pipeline 隱含 graph 原生執行、realtime 隱含降級攤平 instructions，並註明部署層 `AGENT_MODE` 可覆蓋實際路徑。**文案以結果優先**（先講「realtime 下 graph 分支不會驅動對話」，再講機制）。header 既有「需 pipeline 部署」badge 仍正確，保留。
- **validator parity：補 `tool_result_condition` warning**：前端 `frontend/lib/agent-graph.ts` 的 `validateGraph` 補上「`trigger: tool_result` 且 `condition` 非空」warning（v1 視為無條件、condition 被忽略），對齊後端 `agents/runtime/graph.py` 既有同碼規則。純函數，vitest 覆蓋。

## Capabilities

### Modified Capabilities
- `graph-editor-ux`: (1) 以「依 profile 宣告 mode 的執行狀態指示（並註明部署 env 可覆蓋）」取代過期的「Interim Try/deploy degradation banner」requirement；(2)「Graph structure validation feedback」requirement 新增 `tool_result` 邊帶非空 condition 的 warning（前後端 parity）。

## Impact

- **Frontend**：`profiles/[id]/page.tsx`（條件式文案，取代過期 banner + SaveConfirmModal 字樣）；`lib/agent-graph.ts`（`validateGraph` 新 warning）；`frontend/components/admin/__tests__/`（vitest 新 warning 案例）。
- **後端**：不動（`runtime/graph.py` 已有此規則，本 change 僅補前端 parity）。
- **資料模型**：無變更、無 migration。
- **Out of scope**：模型/語音選擇 UI、global-as-base-layer IA、Stack 面板（全在 `profile-editor-model-voice-ux`）。
