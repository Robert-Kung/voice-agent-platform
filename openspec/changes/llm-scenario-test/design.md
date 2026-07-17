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

1. **Simulator 做為外環，runner 做最小改動（非零改動）。** 現況：`run_profile_llm_text_test` 一次接收完整 messages list 跑完全部輪次，`kind="llm_text"` 硬編碼於 create_run 與事件 payload，無逐輪輸入 hook。scenario 需要的最小 runner 改動明列為三點：(i) 輸入來源抽象——messages list 之外接受 per-turn input provider（callback：拿上一輪 assistant 回覆、回傳下一輪使用者輸入或結束訊號），llm_text 既有呼叫以 list 包成 provider 走同一路徑；(ii) `kind` 與 run 建立參數化（含 case_id），不再硬編碼；(iii) 每輪 assistant 最終回覆回饋 provider。不允許的替代方案：外環每輪帶累積 messages 重呼叫 runner（每次產生新 run row、對前 N-1 輪重打 LLM，成本 ×N 且事件重複）；複製 runner 成獨立 scenario runner（雙份維護）。
2. **criteria 兩型而非統一 NL。** structured criteria 直接斷言 run events（tool_called / tool_not_called / node_reached / handoff_occurred），零 LLM 成本零 flaky，做 gate；NL criteria 走 judge 做 advisory。替代方案「全部 judge」維護成本低一點但 gate flaky 不可接受；「全部 structured」表達不了行為判準（如「未提供脫困指示」）。
3. **資料模型四表**：`scenario_cases`（persona/max_turns/criteria JSON）、`scenario_suites`（case id 有序清單）、`scenario_suite_runs`（suite 執行批次：suite_id、status、彙總 JSON、時間戳）、`scenario_criterion_results`（FK 到 `profile_test_runs`）。case run 沿用 `profile_test_runs`（kind=llm_scenario），加 nullable `case_id` 與 `suite_run_id`——suite 跑兩次或 case 曾單獨執行時，靠 `suite_run_id` 而非 timestamp 分組。criteria 存 JSON 欄位而非獨立表——criteria 只整份讀寫、無跨 case 查詢需求，省一層 join 與 store 維護。
4. **simulator/judge endpoint 為 deployment-level 設定**（env/constants，沿用 AI Generate 的 LM Studio 機制），不可由 API payload 指定（避免 admin API 新增任意 egress 面）；與被測 profile 模型完全分離，simulator/judge usage 不寫入 cost 記錄（僅 log）。judge 理由寫入結果前過 `sanitize_event_payload` 同級 sanitizer。
5. **執行模型：單 case run 同步（與 llm_text 一致）；suite 執行走背景 task**——POST 立即建立 `scenario_suite_runs`（status=running）返回，背景依序跑各 case（避開 LM Studio 併發限制），前端 poll suite run status。並行留為 follow-up。
6. **max_steps 策略**：runner `DEFAULT_MAX_STEPS = 10` 且 graph mode 步數跨 turn 全域累計（prompt mode per-turn 重置）；scenario 執行器呼叫 runner 時 SHALL 傳入 `max_steps = max_turns × 10`，避免 graph profile 長 scenario 在 ~10 步被 `max_steps_reached` 誤終止。不改 graph mode 既有步數語意（llm_text 行為不動）。
7. **種子資料掛 `elevator_repair_graph`**（graph-mode profile），使 node_reached / handoff 型 criteria 有效；以 idempotent seed 實作（獨立 seed marker 記錄「已播種」，admin 刪除後不因重啟復活；seed 於 profile 已存在於 DB 後執行）。

## Risks / Trade-offs

- [simulator 品質決定測試品質——persona 寫不好會測不到目標路徑] → persona prompt 是 case 資料的一部分、可迭代；Pathors 三案例已是驗證過的寫法，直接移植當範本。
- [judge 判定不穩定造成 advisory 噪音] → advisory 定位本身就是緩解；每條附理由讓人快速裁決；不做 gate 就不需要抗 flaky 機制。
- [LM Studio endpoint 不可用時 scenario 跑不動] → simulator 失敗 = run 失敗（明確錯誤訊息）；judge 失敗 = criterion error、gate 不受影響（spec 已定義）。
- [對話終止條件誤判（simulator 不收斂）] → max_turns 硬上限 1–30；終止原因記錄在 run 上供除錯。
- [criteria 與 profile prompt 耦合，prompt 大改後 criteria 過時] → 固有內容維護成本；UI 將 gate fail 與 transcript 並列，讓過時 criteria 一眼可辨。

## Migration Plan

新四表 + `profile_test_runs` 加 nullable `case_id` / `suite_run_id` 欄位，SQLite `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ADD COLUMN` 即可，無資料回填；rollback 只需忽略新表。API 僅新增 endpoint 與 kind 枚舉值（`test_run_store.VALID_RUN_KINDS` 與 routes 的 kind Query pattern 同步擴充），無既有契約變動。

## Open Questions

- simulator 結束訊號的具體 protocol（特殊 token vs structured output）——apply 時依 LM Studio 模型實測擇定，spec 不鎖定。
- structured criterion 各型別的 JSON 欄位形狀（如 `tool_called` 的 required params 名單來源）——task 3.1 定案，前後端共用同一份 schema。
