# Proposal: llm-scenario-test

## Why

LLM Text Test 解決了「不開 room 打真實 LLM」，但多輪使用者輸入仍要人逐輪手打，也沒有自動判定機制——profile 改動後無法一鍵回歸。Pathors 平台上已有「電梯客服-三情境回歸」suite 證明 scenario 式測試（user-simulator + acceptance criteria）對這類語音客服 agent 有效，但它測的是 Pathors 上的鏡像 agent，測不到本平台的 graph runtime、tool wiring 與 quick_ack 語意，且兩邊 prompt 會 drift。需要在本平台 runtime 上做同等能力的自動化情境測試。

## What Changes

- 新增 run kind `llm_scenario`：user-simulator LLM 扮演來電者與 profile 多輪文字對打，執行層復用 `llm_text` runner（graph `goto_*` 路由、工具 dry-run dispatcher、事件 sanitization 全沿用）。
- Test case 持久化：每個 case 含 simulator persona prompt、max_turns、acceptance criteria 清單；case 依附 profile 儲存，可組成 suite 一鍵執行。
- 混合判定：
  - **硬斷言（gate，deterministic）**：以 criteria 的結構化型別對 run events 斷言——工具是否被呼叫／未被呼叫、必填參數是否齊、graph path 是否到達指定 node、handoff 是否發生。
  - **LLM judge（advisory，不擋 gate）**：自然語言 criteria 逐條由 judge LLM 判定 pass/fail + 理由，結果標記為 advisory。
- 結果模型：per-case、per-criterion 結果持久化（沿用 run/event store 模式），suite 執行產出彙總（gate pass/fail + advisory 分數）。
- Simulator 與 judge 的 LLM endpoint 可設定，預設走 LM Studio OpenAI-compatible endpoint（AI Generate 既有路徑），被測 agent 使用 profile 自身模型。
- Profile Editor Test panel 新增 Scenario 分頁：case/criteria CRUD、單 case 執行、suite 執行、對話 transcript 與 per-criterion 結果檢視。
- v1 種子資料：移植 Pathors 電梯三案例（緊急受困／一般報修／非報修諮詢，15 條 criteria 轉為結構化＋NL 混合形式）作為 `elevator_repair` profile 的內建範例 suite。

明確不做（v1 邊界）：

- 不做語音層（無 room / STT / TTS），文字層 scenario 即涵蓋目標。
- 不做 CI 自動排程與 token 預算控管（手動觸發；排程是 follow-up）。
- 不做真實副作用模式——scenario run 一律走 dry-run dispatcher，無例外開關。
- 不做 Pathors 雙向同步；只做一次性內容移植。
- judge 不當 gate；不做 judge 多數決/重試等抗 flaky 機制（advisory 定位下不需要）。

## Capabilities

### New Capabilities

- `profile-scenario-test`: scenario 測試能力——test case/criteria/suite 資料模型、user-simulator 對打執行、混合判定（結構化硬斷言 gate + LLM judge advisory）、per-criterion 結果與 UI。

### Modified Capabilities

- `profile-llm-text-test`: 「Run kind 區分與 API 相容」requirement 的 kind 枚舉自 `flow | llm_text` 擴充為 `flow | llm_text | llm_scenario`；既有兩種 kind 的行為與 API 契約不變。

## Impact

- `agents/api/routes_profile_test_runs.py` — kind 擴充、scenario case/suite CRUD 與執行 endpoints。
- `agents/runtime/`（llm_text runner 所在模組）— simulator 迴圈包裝層、判定引擎（event 斷言 + judge 呼叫）。
- `agents/db/` — scenario case / criteria / suite / criterion result 資料表與 store。
- `agents/profiles/elevator_repair.yaml` 或 seed 機制 — 內建範例 suite。
- `frontend/components/admin/`（Test panel）— Scenario 分頁。
- `agents/tests/` + `frontend` vitest — 新增對應測試。
- 不影響：Flow Test 與 LLM Text Test 既有契約、runtime 生產路徑、cost 計算（scenario 的被測 LLM usage 沿用既有 usage 記錄）。
