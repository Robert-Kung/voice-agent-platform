# Tasks: llm-scenario-test

## 1. 資料層

- [ ] 1.1 新增 `scenario_cases` / `scenario_suites` / `scenario_criterion_results` 資料表與 SQLAlchemy models（criteria 為 JSON 欄位；`profile_test_runs` 加 nullable `case_id`）
- [ ] 1.2 store 層：case/suite CRUD、criterion result 寫入與查詢（依附 profile 與 run），含 suite 引用 case 刪除行為
- [ ] 1.3 db 層測試（models + store，含 criteria JSON round-trip 與非法型別驗證）

## 2. 執行層

- [ ] 2.1 simulator client：persona prompt → 逐輪使用者輸入生成（LM Studio OpenAI-compatible endpoint，沿用 AI Generate 設定機制），含結束訊號 protocol 實測擇定
- [ ] 2.2 scenario 執行器：simulator 外環 loop 包裝 `llm_text_runner`（輸入來源替換，不改 runner 內核），終止條件（max_turns / 結束訊號 / handoff）與終止原因記錄
- [ ] 2.3 判定引擎：structured criteria 對 run events 的 deterministic 斷言（tool_called / tool_not_called / node_reached / handoff_occurred + 參數必填檢查）→ gate 結果
- [ ] 2.4 judge client：NL criteria 逐條判定 pass/fail + 理由，advisory 標記；judge 失敗 → criterion error 不影響 gate
- [ ] 2.5 執行層測試（mock simulator/judge：多輪 loop、三種終止、gate 彙總、judge error 路徑、dry-run 無副作用）

## 3. API 層

- [ ] 3.1 case/suite CRUD endpoints + `kind: llm_scenario` run 建立（帶 case_id 參照）、run detail 含 per-criterion 結果
- [ ] 3.2 suite 執行 endpoint（依序跑 case，彙總 gate/advisory）與 suite 執行歷史查詢
- [ ] 3.3 API 測試（kind 枚舉相容性：flow/llm_text 契約不變、list kind 過濾含 llm_scenario）

## 4. 種子資料

- [ ] 4.1 Pathors 電梯三案例移植為 `elevator_repair` 範例 suite（15 條 criteria 轉 structured + nl 混合），idempotent seed

## 5. 前端

- [ ] 5.1 Test panel Scenario 分頁：case/criteria CRUD 表單、suite 組建
- [ ] 5.2 執行與結果檢視：單 case / suite 執行、進行狀態、transcript + per-criterion 結果（gate 與 advisory 視覺區分）
- [ ] 5.3 前端測試（vitest：表單驗證、結果呈現、kind 相容）

## 6. 收尾

- [ ] 6.1 全套測試綠（backend pytest + frontend vitest）；docs 同步（CLAUDE.md 殘項、ARCHITECTURE 若有觸及）
- [ ] 6.2 對真實 LM Studio endpoint 跑一次 elevator 範例 suite 的 live 驗證並記錄結果
