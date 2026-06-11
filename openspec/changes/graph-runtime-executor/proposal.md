## Why

`graph-agent-builder` 提供 graph 的設計時 UX 與資料模型、`multi-model-runtime` 提供模型解析——但 graph 的 **runtime 執行語意**在 2026-06-10 的 eng review 中被確認為責任真空：兩提案互相指向對方，誰都沒認領。本 change 正式認領：把 profile config 的 `graph` 區塊（見 `graph-agent-builder` 的 `graph-agent-schema` spec，為兩 change 間的凍結契約）在 LiveKit Agents runtime 上執行起來。

> 本 proposal 目前為 review 定案後的 mandate 骨架；完整 design / tasks 待 `graph-agent-builder` schema 落地後以 `/opsx:propose` 流程補齊。

## What Changes

- **執行機制（review T4 定案，[Layer 1]）**：不自建狀態機。以 LiveKit Agents SDK 原生 multi-agent handoff 組裝——每個 graph node 對應一個 Agent instance（focused prompt = `global_prompt` + node `prompt`，tools = node `tools`），edge 轉移以 tool-returned Agent handoff 實現。design 須記錄與自建狀態機的比較。
- **Edge 觸發語意**：`trigger: user_turn` 邊在使用者回合後評估 NL `condition`（LLM 評估）；`trigger: tool_result` 邊在工具回傳後依結果轉移（電梯案例的「建單後立即轉接」）。多邊命中時依 `edges` 陣列順序取第一個。
- **模式邊界（review T2 定案）**：v1 graph 執行**僅支援 pipeline mode**。realtime（TextInputRealtimeModel / Gemini Live）的 graph 執行為 open question，須先 spike 驗證「節點切換不破壞延遲規避架構」才能納入——instructions 在 Gemini Live 連線時綁定，中途換 prompt 的成本未知。
- **策略來源 gate（review D2 定案）**：`editor_mode === 'graph'` 且 graph 通過**後端 Python validator**（本 change 認領，為 runtime gate 的唯一真相；前端 `validateGraph` 僅 UX 提示）才走 graph 執行；否則 fallback 到 profile 的 `instructions`（由 graph-agent-builder 在每次存檔時自動重生，不會過期）+ 啟動 log warning。對話策略壞掉不 fail loud——來電者不該聽到斷線。
- **全域能力注入**：QA inline / services hours 維持 global 層注入（併入 global_prompt 組合），不下沉到 node。`human_operator` 的 handoff 行為由 `handoff` node 觸發 `transfer_to_human`，node `prompt` 作為 per-handoff greeting。
- **Per-node 模型（multi-model-runtime OQ4 介面點)**：node 若宣告 model spec，呼叫 `agents/runtime/providers.py` 的同一組 `build_*`；cost 依 session row 的可擴充模型名結構（multi-model task 2.5a）分段記錄。v1 可只留介面不實作。

## Capabilities

### New Capabilities
- `graph-execution`: graph 的 runtime 執行——SDK handoff 組裝、edge 觸發評估、策略來源 gate 與 fallback、全域能力注入、pipeline-only 邊界。
- `graph-runtime-validation`: 後端 Python graph validator——與前端 `validateGraph` 同規則集（唯一 start、可達性、邊端點、trigger 合法值），作為執行 gate 的唯一真相；API 存檔時的硬驗證亦掛此 validator（解前端可繞過問題）。

## Impact

- **Code**：`agents/agent_factory.py`（graph → Agent class 組裝）、`agents/agent.py`（session 分支）、新增 `agents/runtime/graph.py`（validator + executor 組裝）、`agents/api/routes_profiles.py`（存檔掛 validator）。
- **依賴順序**：依賴 `graph-agent-builder` 的 schema（含 `schema_version: 1`、edge `trigger`）與 `multi-model-runtime` 的 `resolve_session_components`。兩者落地後開工。
- **Out of scope**：graph 編輯器 UX（graph-agent-builder）、模型 provider 解析（multi-model-runtime）、realtime graph 執行（spike 後另議）。
