# Spec Delta: profile-llm-text-test (llm-scenario-test)

## MODIFIED Requirements

### Requirement: Run kind 區分與 API 相容

系統 SHALL 以 `kind` 欄位（`flow` | `llm_text` | `llm_scenario`）區分三種 run；既有 Flow Test API 契約 MUST 保持不變（未帶 kind 的既有 request 預設為 flow），既有 `llm_text` run 的行為與 API 契約 MUST 保持不變。

#### Scenario: 建立 llm_text run

- **WHEN** POST test-runs 帶 `kind: llm_text`
- **THEN** 系統建立並執行 LLM-backed run，detail response 含 kind 欄位

#### Scenario: 既有 flow test 不受影響

- **WHEN** POST test-runs 未帶 kind（既有契約）
- **THEN** 系統執行 deterministic flow test，行為與 `profile-test-runs` 規格一致

#### Scenario: List 依 kind 過濾

- **WHEN** GET test-runs list 帶 kind query 參數
- **THEN** 僅回傳該 kind 的 runs

#### Scenario: 建立 llm_scenario run

- **WHEN** POST test-runs 帶 `kind: llm_scenario` 與 case 參照
- **THEN** 系統建立並執行 scenario run（行為定義於 `profile-scenario-test` 規格），detail response 含 kind 欄位
