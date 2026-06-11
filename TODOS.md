# TODOS

## Models 設定面板（admin UI）

- **What**: Profile Editor 右側面板新增 Models section，編輯 `models` 區塊（mode、LLM/STT/TTS provider+model fallback 清單、realtime 變體/voice）。
- **Why**: `multi-model-runtime` 落地後 `models` 區塊只能在 Advanced JSON 生肉編輯——能用不會壞（後端 Pydantic 422 擋格式錯誤），但對非工程師不友善。2026-06-10 eng review（graph-agent-builder D6）定案：記 TODO、不擴當期任一提案 scope。
- **Pros**: 模型選擇防呆（provider enum、realtime allowlist 下拉化）；與 per-node 模型選擇（graph-runtime-executor 的 OQ4 介面點）一次做對。
- **Cons**: 驗證規則目前仍在 multi-model-runtime §3 實作中，UI 先行會做出不同步的驗證。
- **Context**: `frontend/hooks/use-profile-form.ts` 的 `KNOWN_KEYS` 目前不含 `models`（落入 extra → Advanced JSON，round-trip 安全已驗證）。做的時候：KNOWN_KEYS 加 `models`、右側面板照既有 CollapsibleSection 模式加 section、enum 來源對齊 `agents/runtime/providers.py` 的 `KNOWN_DIRECT_PROVIDERS` 與 realtime allowlist。
- **Depends on / blocked by**: multi-model-runtime §3（schema 驗證）落地；建議等 graph-runtime-executor 的 per-node model 介面定案後一次設計。
