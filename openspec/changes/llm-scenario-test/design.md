# Design: llm-scenario-test

## Context

`agents/runtime/llm_text_runner.py` 已提供多輪 LLM 文字對打的完整執行層：profile 載入與 normalization、graph `goto_*` transition tools 合成、domain tool dry-run dispatcher、事件 sanitization、`profile_test_runs` / `profile_test_run_events` 持久化（`db/test_run_store.py`）。目前每輪使用者輸入由前端人工提供。Pathors 的測試模型（simulator persona + maxTurns + per-criterion 判定）已在電梯專案驗證可行，本 change 把該模型落到本平台 runtime 上。

## Goals / Non-Goals

**Goals:**

- 一鍵回歸：profile 儲存後不需人工逐輪輸入即可跑完整情境並得到 pass/fail。
- 判定可信：gate 結果零 flaky（僅 deterministic 斷言），LLM 判定明確標示 advisory。
- 最大化復用：不複製 llm_text runner，simulator 只是輸入來源的替換層。

**Non-Goals:**

- 語音層 e2e、CI 排程、token 預算控管、真實副作用模式、Pathors 同步（見 proposal 邊界）。

## Decisions

1. **Simulator 做為 llm_text runner 的外環，不改 runner 內核。** runner 現有介面接受「下一輪使用者輸入」；scenario 執行器以 loop 呼叫 simulator LLM 產生輸入、餵入 runner、取回覆再回饋 simulator，直到終止條件。替代方案是把 simulator 塞進 runner 內部——會讓 llm_text 與 llm_scenario 耦合、runner 需要感知兩種模式，放棄。
2. **criteria 兩型而非統一 NL。** structured criteria 直接斷言 run events（tool_called / tool_not_called / node_reached / handoff_occurred），零 LLM 成本零 flaky，做 gate；NL criteria 走 judge 做 advisory。替代方案「全部 judge」維護成本低一點但 gate flaky 不可接受；「全部 structured」表達不了行為判準（如「未提供脫困指示」）。
3. **資料模型獨立三表**：`scenario_cases`（persona/max_turns/criteria JSON）、`scenario_suites`（case id 有序清單）、criterion 結果掛在既有 run 上（新表 `scenario_criterion_results`，FK 到 `profile_test_runs`）。criteria 存 JSON 欄位而非獨立表——criteria 只整份讀寫、無跨 case 查詢需求，省一層 join 與 store 維護。run 本身沿用 `profile_test_runs`（kind=llm_scenario，附 case_id 參照欄位）。
4. **simulator/judge endpoint 沿用 AI Generate 的 LM Studio 設定機制**（env/constants），與被測 profile 模型完全分離；simulator/judge usage 不寫入 cost 記錄（僅 log）。
5. **suite 執行 v1 依序跑**，避免 LM Studio 單機併發限制與 run store 競爭；並行留為 follow-up。
6. **種子資料以 idempotent seed（首次啟動或 migration 時插入，之後不再覆蓋）**，滿足「可編輯刪除、不隨重啟還原」。

## Risks / Trade-offs

- [simulator 品質決定測試品質——persona 寫不好會測不到目標路徑] → persona prompt 是 case 資料的一部分、可迭代；Pathors 三案例已是驗證過的寫法，直接移植當範本。
- [judge 判定不穩定造成 advisory 噪音] → advisory 定位本身就是緩解；每條附理由讓人快速裁決；不做 gate 就不需要抗 flaky 機制。
- [LM Studio endpoint 不可用時 scenario 跑不動] → simulator 失敗 = run 失敗（明確錯誤訊息）；judge 失敗 = criterion error、gate 不受影響（spec 已定義）。
- [對話終止條件誤判（simulator 不收斂）] → max_turns 硬上限 1–30；終止原因記錄在 run 上供除錯。
- [criteria 與 profile prompt 耦合，prompt 大改後 criteria 過時] → 固有內容維護成本；UI 將 gate fail 與 transcript 並列，讓過時 criteria 一眼可辨。

## Migration Plan

新表 + `profile_test_runs` 加 nullable `case_id` 欄位，SQLite `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ADD COLUMN` 即可，無資料回填；rollback 只需忽略新表。API 僅新增 endpoint 與 kind 枚舉值，無既有契約變動。

## Open Questions

- simulator 結束訊號的具體 protocol（特殊 token vs structured output）——apply 時依 LM Studio 模型實測擇定，spec 不鎖定。
