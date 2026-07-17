# Spec Delta: profile-scenario-test (llm-scenario-test)

## ADDED Requirements

### Requirement: Scenario test case 資料模型
系統 SHALL 允許 admin 對已存 profile 建立、編輯、刪除 scenario test case。每個 case SHALL 包含：名稱、simulator persona prompt（自由文字，描述來電者人設、背景事實與行為規則）、max_turns（上限值受驗證，1–30）、acceptance criteria 清單。每條 criterion SHALL 為以下兩型之一：

- **structured**：型別化斷言，型別 SHALL 至少涵蓋 `tool_called`（含可選參數必填檢查）、`tool_not_called`、`node_reached`、`handoff_occurred`。
- **nl**：自然語言描述，由 judge LLM 判定。

case SHALL 可組成 suite（名稱 + case id 有序清單）；suite 與 case 依附 profile 儲存與查詢。

#### Scenario: 建立含混合 criteria 的 case
- **WHEN** admin 對 profile 建立 case，criteria 含一條 `tool_called: create_maintenance_ticket`（required params 檢查）與一條 nl「客服全程未提供脫困指示」
- **THEN** case 持久化成功，兩條 criteria 各自保留型別與內容

#### Scenario: 非法 criterion 型別被拒
- **WHEN** 建立 case 時 criterion 型別不在允許集合
- **THEN** API 回 422 並指明非法欄位

#### Scenario: Suite 引用被刪除的 case
- **WHEN** 刪除仍被 suite 引用的 case
- **THEN** 系統拒絕刪除或同步自 suite 移除該引用（擇一，行為一致並在 response 說明）

### Requirement: User-simulator 對打執行
`kind: llm_scenario` 的 run SHALL 由 simulator LLM 依 case 的 persona prompt 生成每一輪使用者輸入，與被測 profile 進行多輪文字對話；被測方執行語意 SHALL 與 `llm_text` run 一致（profile 自身 LLM、graph `goto_*` 路由、工具 dry-run dispatcher、事件 sanitization）。scenario run 的工具執行 MUST 強制 dry-run：request 指定其他 tool_execution_mode 時 API 回 422。對話 SHALL 於下列任一條件終止：達到 max_turns、simulator 輸出結束訊號、被測方觸發 handoff/結束節點。simulator 與 judge 的 LLM endpoint SHALL 於 deployment 層設定（不可由 API request 指定），預設為既有 LM Studio OpenAI-compatible endpoint；simulator/judge 呼叫 MUST NOT 計入被測 profile 的 usage/cost 記錄。simulator 呼叫失敗（連線失敗/逾時）時 run SHALL 以 failed 終結並記錄 error event，MUST NOT 遺留 running 狀態。

#### Scenario: 多輪對打並記錄 transcript
- **WHEN** 對含 graph 的 profile 執行 scenario run
- **THEN** simulator 逐輪生成輸入、被測方逐輪回覆，全部 turn 依序記錄為 run events，graph 轉移與 tool call 事件與 llm_text run 同格式

#### Scenario: 達到 max_turns 終止
- **WHEN** 對話進行至 max_turns 仍未自然結束
- **THEN** run 標記終止原因為 max_turns 並照常進入判定階段

#### Scenario: 無副作用
- **WHEN** scenario run 中被測方呼叫帶 HTTP endpoint 的 domain tool
- **THEN** 系統走 dry-run dispatcher，不發出真實 HTTP 請求

#### Scenario: 指定 live 工具模式被拒
- **WHEN** POST 建立 scenario run 時帶 `tool_execution_mode: live`
- **THEN** API 回 422

#### Scenario: simulator 不可用
- **WHEN** simulator endpoint 連線失敗或逾時
- **THEN** run 以 failed 終結並含 error event，不遺留 running 狀態

### Requirement: 混合判定與結果模型
run 結束後系統 SHALL 對每條 criterion 產出結果並持久化。structured criteria SHALL 以 run events 做 deterministic 斷言，結果為 pass/fail，並彙總為 run 的 **gate 結果**（全部 structured pass 才 gate pass）。nl criteria SHALL 由 judge LLM 依完整 transcript 逐條判定 pass/fail 並附一句理由，結果標記為 **advisory**，MUST NOT 影響 gate 結果。judge 呼叫失敗時該條 criterion SHALL 標記為 `error`（非 fail），不影響 gate。

#### Scenario: structured fail 導致 gate fail
- **WHEN** criteria 含 `tool_called: create_maintenance_ticket` 但 run events 中無該 tool call
- **THEN** 該 criterion fail，run gate 結果為 fail，其餘 criteria 仍逐條產出結果

#### Scenario: nl criterion 不影響 gate
- **WHEN** 所有 structured criteria pass、一條 nl criterion 被 judge 判 fail
- **THEN** run gate 結果為 pass，該 nl criterion 顯示 advisory fail 與理由

#### Scenario: judge 不可用
- **WHEN** judge endpoint 連線失敗
- **THEN** nl criteria 標記 error 並附錯誤摘要，gate 結果不受影響，run 整體不視為執行失敗

#### Scenario: graph 未生效時的 node/handoff criteria
- **WHEN** criteria 含 `node_reached` 或 `handoff_occurred`，但 run 實際以非 graph 路徑執行（prompt-mode profile，或 graph 驗證失敗 fallback）
- **THEN** 該類 criterion 判 fail 並附明確原因（graph 未生效 + fallback reason）——graph 失效本身即回歸訊號，gate 結果如實反映

### Requirement: Suite 執行與彙總
系統 SHALL 支援一鍵執行 suite：建立 suite 執行批次紀錄（含 status，可輪詢）後於背景依序對 suite 內每個 case 建立 scenario run，完成後產出 suite 層彙總——每 case 的 gate 結果、advisory 通過數/總數、失敗 criterion 摘要。各 case run SHALL 記錄所屬批次，使同一 suite 的多次執行與 case 的單獨執行可明確區分；suite 執行歷史 SHALL 可查詢並連結至各 case run detail。

#### Scenario: Suite 執行彙總
- **WHEN** 執行含 3 個 case 的 suite，其中 1 個 case gate fail
- **THEN** 彙總顯示 2 pass / 1 fail，fail case 可展開至 per-criterion 結果與 transcript

### Requirement: Profile Editor Scenario UI
Profile Editor Test panel SHALL 新增 Scenario 分頁：case 與 criteria 的 CRUD、suite 組建、單 case 與 suite 執行、run 結果檢視（對話 transcript、per-criterion pass/fail/advisory/error 與理由）。執行中 SHALL 顯示進行狀態；UI 呈現 MUST 明確區分 gate 結果與 advisory 結果。

#### Scenario: 檢視 run 結果
- **WHEN** admin 開啟一筆完成的 scenario run
- **THEN** 可見完整 transcript、structured criteria 的 pass/fail、nl criteria 的 advisory 標記與 judge 理由

### Requirement: 電梯範例 suite 種子資料
系統 SHALL 為 `elevator_repair_graph` profile（graph-mode，使 node/handoff 型 criteria 有效）提供內建範例 suite（Pathors 三案例移植：緊急受困、一般報修、非報修諮詢），criteria 以 structured + nl 混合形式表達；種子資料 SHALL 可被 admin 編輯或刪除，不隨系統重啟還原。

#### Scenario: 種子 suite 可用
- **WHEN** 系統初始化後 admin 開啟 elevator_repair_graph 的 Scenario 分頁
- **THEN** 可見範例 suite 與三個 case，可直接執行

#### Scenario: 刪除後不復活
- **WHEN** admin 刪除種子 suite 後系統重啟
- **THEN** 種子 suite 不重新出現
