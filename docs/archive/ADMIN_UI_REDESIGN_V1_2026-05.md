# Admin UI 重新設計 V1（2026-05-12 ~ 2026-05-14）

> 已完成。歸檔紀錄。後續改版見 CLAUDE.md「Profile Editor v2」章節。

## 設計方向
- **美感**：Dark-first Developer Console（Linear/Vercel 風），保留 light/dark 切換
- **Layout**：Collapsible sidebar navigation，取代原有 top-nav
- **重點功能**：Agent Flow Builder — 用 `@xyflow/react` 視覺化 profile 的組裝邏輯
- **範圍**：僅 `/admin/*` 路徑；首頁 voice testing 維持現狀

## 完成項目

| # | 內容 | 狀態 |
|---|------|------|
| 1 | Sidebar layout + Dark-first 色彩系統 | ✅ |
| 2 | Agent Flow Builder（Profile 編輯內嵌 xyflow node-graph） | ✅ |
| 3 | Dashboard 增強（趨勢圖 + real-time indicators） | ✅ |
| 4 | web-design-guidelines review pass | ✅ |

## Agent Flow Builder 設計

因 realtime mode + Gemini 模型已固定最佳配置，Flow Builder 不控制底層 STT/LLM/TTS 選擇。
重點是視覺化**「Profile 的對話能力組裝」**：

```
[Instructions] → [QA Database] → [Service Hours] → [Tools]
                                                      ├─ get_current_time
                                                      ├─ transfer_to_human
                                                      └─ HTTP Tool × N
```

節點類型：
- **Prompt** — system instructions 編輯（主節點）
- **QA Database** — inline/tool mode 切換 + QA 條目管理
- **Service Hours** — 營業時間結構化設定
- **Human Handoff** — 轉接設定
- **Built-in Tool** — get_current_time 等可選掛載
- **HTTP Tool** — Tier 3 自定義 API 呼叫（可多個）

互動：
- 從左側 palette 拖入節點 → 連接到 Agent 主節點
- 點選節點 → 右側 panel 顯示該區塊的詳細設定表單
- 儲存時自動 serialize 回 profile config JSON
