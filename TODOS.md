# TODOS

## Models 設定面板（admin UI）

- **What**: Profile Editor 右側面板新增 Models section，編輯 `models` 區塊（mode、LLM/STT/TTS provider+model fallback 清單、realtime 變體/voice）。
- **Why**: `multi-model-runtime` 落地後 `models` 區塊只能在 Advanced JSON 生肉編輯——能用不會壞（後端 Pydantic 422 擋格式錯誤），但對非工程師不友善。2026-06-10 eng review（graph-agent-builder D6）定案：記 TODO、不擴當期任一提案 scope。
- **Pros**: 模型選擇防呆（provider enum、realtime allowlist 下拉化）；與 per-node 模型選擇（graph-runtime-executor 的 OQ4 介面點）一次做對。
- **Cons**: 驗證規則目前仍在 multi-model-runtime §3 實作中，UI 先行會做出不同步的驗證。
- **Context**: `frontend/hooks/use-profile-form.ts` 的 `KNOWN_KEYS` 目前不含 `models`（落入 extra → Advanced JSON，round-trip 安全已驗證）。做的時候：KNOWN_KEYS 加 `models`、右側面板照既有 CollapsibleSection 模式加 section、enum 來源對齊 `agents/runtime/providers.py` 的 `KNOWN_DIRECT_PROVIDERS` 與 realtime allowlist。
- **Depends on / blocked by**: multi-model-runtime §3（schema 驗證）落地；建議等 graph-runtime-executor 的 per-node model 介面定案後一次設計。

## CI：自動跑前後端測試（P1）

- **What**: 加 GitHub Actions workflow，PR / push 時跑 `frontend: pnpm install --frozen-lockfile && pnpm test`（28→43 vitest）與 `agents: uv run pytest tests/ -q`（199）。
- **Why**: 2026-06-12 /review（testing specialist）指出 repo 完全沒有 CI 跑測試——`.github/workflows/` 只有 Claude review 自動化。任何人改壞測試都不會被擋，測試套件價值取決於有沒有人記得手動跑。
- **Context**: frontend 在 node 18 下需 vitest3+vite6（lockfile 已 pin）；CI 環境可直接用 node 20+ 免 pin。agents 用 uv。

## Graph 編輯器殘項（2026-06-12 /review 低優先）

- **M7 canvas 打字重建**: NodeInspector/Global Prompt 打字每鍵觸發 `GraphCanvas` 的 graph-effect 重建全部 React Flow nodes/edges。<50 節點下毫秒級、無使用者可感差異。若 graph 變大：在 effect 內 merge 未變更節點的舊參照，或讓 prompt-only 編輯跳過重建（`frontend/components/admin/graph-canvas.tsx` 的 useEffect）。
- **L6 style map 跨模組 cast**: `graph-canvas.tsx` 從 `agent-flow-builder.tsx` import NODE_ICONS/COLORS（FlowNodeType keyed），靠 `n.type as FlowNodeType` cast 橋接 GraphNodeType——未來 GraphNodeType 加值時編譯不會抓到 map 缺項。解法：抽 GraphNodeType-keyed 子集到 `frontend/lib/agent-graph-style.ts`，FlowNodeType 回歸純 legacy。
- **L9 範例 yaml 攤平同步測試**: `agents/profiles/elevator_repair_graph.yaml` 的 instructions 是 graphToPrompt 輸出的手工拷貝，無測試保證與 graph 同步（YAML 手改會 bypass 編輯器重生機制）。解法：vitest 加 yaml parse（js-yaml devDep）斷言 `instructions === graphToPrompt(config.graph)`。
