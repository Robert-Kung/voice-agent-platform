## Why

`graph-agent-builder` 提供 graph 的設計時 UX 與資料模型、`multi-model-runtime` 提供模型解析——但 graph 的 **runtime 執行語意**在 2026-06-10 的 eng review 中被確認為責任真空：兩提案互相指向對方，誰都沒認領。本 change 正式認領：把 profile config 的 `graph` 區塊（見 `graph-agent-builder` 的 `graph-agent-schema` spec，為兩 change 間的凍結契約）在 LiveKit Agents runtime 上執行起來。

## What Changes

- **執行機制（review T4 定案，[Layer 1]）**：不自建狀態機。以 LiveKit Agents SDK 原生 multi-agent handoff 組裝——每個 graph node 對應一個 Agent instance（focused prompt = `global_prompt` + node `prompt`，tools = node `tools`），edge 轉移以 tool-returned Agent handoff 實現（SDK `generation.py` 確認 function tool 回傳 `Agent` 即觸發 handoff）。design 須記錄與自建狀態機的比較。
- **Edge 觸發語意**：`trigger: user_turn` 邊在使用者回合後評估 NL `condition`（LLM 評估）；`trigger: tool_result` 邊在 domain tool 回傳後**無條件立即轉移**（電梯案例的「建單後立即轉接」），實現為 domain tool 直接回傳目標 Agent。多邊命中時依 `edges` 陣列順序取第一個。**v1 不支援 `tool_result` 邊的非空 `condition`**：schema 無 tool↔edge 綁定欄位、零驗證案例，且會在最延遲敏感的 post-tool 點塞入非確定性 LLM 判定；validator 對「tool_result + 非空 condition」發 warning，runtime 一律當無條件處理。真案例出現再以 `schema_version` bump 加結構化綁定。
- **模式邊界 —— graph 與 realtime 互斥（mode 耦合）**：graph 執行**僅 pipeline mode**，且這是**完整生產路徑**（profile 設 `models.mode: pipeline` 即可上 SIP，非 demo-only）。realtime 下 graph 執行今天是 **broken 而非 slow**：SDK handoff 會對 live Gemini 連線呼叫 `update_instructions`，但 `gemini-2.5-flash-native-audio`（預設）走 mid-session `send_client_content` → 第一個 model turn 後遭 Gemini **1007 拒絕**；`gemini-3.1-flash-live-preview` 則**靜默忽略** node 新 instructions（停在 start node prompt）。故：
  - **save-time 阻擋**：`editor_mode: graph` + `models.mode: realtime` → 後端 validator 回 422；前端編輯器 disable realtime 切換。此組合選不出來。
  - **runtime 兜底**：若 deployment 級 `AGENT_MODE=realtime` env 蓋過 profile（env 優先）讓 graph profile 仍落 realtime，降級跑攤平 `instructions` + 大聲 warning，**絕不 fail loud**——`ctx.delete_room()` 技術上能掛電話，但 SIP profile 由 secret 綁死、無任何 UI banner，掛斷 = 靜默生產事故。
  - realtime + graph 解鎖為**獨立 follow-up change**（需先 spike），非本 v1 的債。
- **策略來源 gate（review D2 定案）**：`editor_mode === 'graph'` 且 graph 通過**後端 Python validator** 且 effective mode 為 `pipeline`（本 change 認領，validator 為 runtime gate 的唯一真相；前端 `validateGraph` 僅 UX 提示）才走 graph 執行；否則 fallback 到 profile 的 `instructions`（由 graph-agent-builder 在每次存檔時自動重生，不會過期）+ 啟動 log warning。對話策略壞掉不 fail loud——來電者不該聽到斷線。
- **全域能力注入**：QA inline / services hours 維持 global 層注入（併入 global_prompt 組合），不下沉到 node。`human_operator` 的 handoff 行為由 `handoff` node 觸發 `transfer_to_human`，node `prompt` 作為 per-handoff greeting。
- **Per-node 模型（multi-model-runtime OQ4 介面點)**：node 若宣告 model spec，呼叫 `agents/runtime/providers.py` 的同一組 `build_*`；cost 依 session row 的可擴充模型名結構（multi-model task 2.5a）分段記錄。v1 可只留介面不實作。

## Capabilities

### New Capabilities
- `graph-execution`: graph 的 runtime 執行——SDK handoff 組裝、edge 觸發評估、策略來源 gate 與 fallback、全域能力注入、pipeline-only 邊界。
- `graph-runtime-validation`: 後端 Python graph validator——與前端 `validateGraph` 同規則集（唯一 start、可達性、邊端點、trigger 合法值），作為執行 gate 的唯一真相（它是 gate 的共同依賴，executor 沒它寫不出來——這是它先做的真正理由，不是「堵直接打 API 的洞」：executor 上線前 invalid graph 只會被攤平成無害 instructions，無可利用面）。同時新增兩條本 change 專屬規則：**graph + realtime mode 互斥**（save 回 422）、**tool_result 邊非空 condition** 發 warning。

## Impact

- **Code**：`agents/agent_factory.py`（graph → Agent class 組裝）、`agents/agent.py`（session 分支）、新增 `agents/runtime/graph.py`（validator + executor 組裝）、`agents/api/routes_profiles.py`（存檔掛 validator + graph/realtime 互斥 422）、前端編輯器（graph mode 時 disable realtime 切換，UX 提示）。
- **依賴順序**：依賴 `graph-agent-builder` 的 schema（含 `schema_version: 1`、edge `trigger`）與 `multi-model-runtime` 的 `resolve_session_components`。兩者均已落地，可開工。
- **Out of scope**：graph 編輯器 UX（graph-agent-builder）、模型 provider 解析（multi-model-runtime）、realtime graph 執行（獨立 follow-up，需先 spike）。
