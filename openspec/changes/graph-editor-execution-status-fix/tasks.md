## 1. validator parity（純函數）

- [ ] 1.1 `frontend/lib/agent-graph.ts` 的 `validateGraph` 新增 warning：edge `edgeTrigger(e) === 'tool_result'` 且 `condition.trim()` 非空 → code `tool_result_condition`，文案說明 v1 視為無條件、condition 會被忽略（對齊後端 `agents/runtime/graph.py:202-210` 同碼意）
- [ ] 1.2 vitest 補測試：tool_result + 非空 condition → 觸發；tool_result + 空 condition → 不觸發；`trigger: undefined` + 非空 condition → **不**觸發（前後端 `edgeTrigger` 都 coerce 成 user_turn）；user_turn + condition → 不觸發
- [ ] 1.3 確認其餘 error/warning 與後端 parity（無回歸）

## 2. 過期執行狀態文案（依 profile 宣告 mode）

- [ ] 2.1 grep `graph-runtime-executor` / `fallback` / `待落地` 全面盤點 `frontend/`，列出所有過期文案點
- [ ] 2.2 `profiles/[id]/page.tsx` 中央 banner（~L124-128）改為依 profile 宣告 `models.mode` 條件式：pipeline→graph 原生執行、realtime→降級攤平。**文案結果優先**（先講「realtime 下 graph 分支不會驅動對話」再講機制）
- [ ] 2.3 `SaveConfirmModal`（~L297-302）graph 目標文案同步條件化，移除「graph-runtime-executor 落地前」字眼
- [ ] 2.4 文案註明部署層 `AGENT_MODE` 可覆蓋實際路徑；spec 不宣稱知道 runtime 實際路徑
- [ ] 2.5 保留 header「需 pipeline 部署」badge（仍正確）；prompt-mode「最近一次攤平結果」提示不動

## 3. 驗證

- [ ] 3.1 vitest 全綠（validateGraph 新 warning 案例）
- [ ] 3.2 frontend build 通過；後端 `cd agents && uv run pytest tests/ -q` 不受影響（本 change 不動後端）
- [ ] 3.3 瀏覽器 QA：graph 模式 banner 依 mode 正確（不再出現「待 executor 落地」）；pipeline vs realtime 文案各自正確
- [ ] 3.4 `openspec validate graph-editor-execution-status-fix --strict` 通過
