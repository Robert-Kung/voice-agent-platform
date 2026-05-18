# V2 Profile Editor — 修繕清單

> Design review baseline: 2026-05-15
> Audit reference: /home/user/.gstack/projects/Robert-Kung-first-livekit/designs/design-audit-20260515/
> 對應 CLAUDE.md 任務表項 9 (Docker build 驗證 + 瀏覽器 QA)

---

## 已實作（review 原本誤判為缺）

- ✅ `sonner` toast：admin layout 已掛 Toaster，`handleSave` / `handleTry` 已 toast 成功/失敗
- ✅ `beforeunload` warning：`use-profile-form.ts:343-351` dirty 時阻擋關閉/重整
- ✅ Section badges：tools / qa / hours / handoff / identity / advanced 全部有
- ✅ Section defaultOpen 智能：有內容才預設展開

---

## Sprint A — 必修（GA 前）

### A1. AI Generate Modal 關閉與覆寫保護
**檔案**：`frontend/app/admin/(authenticated)/profiles/[id]/v2/page.tsx`（`GeneratePromptModal` 元件）

**問題**：
- Escape 鍵無法關閉
- Backdrop 點擊無法關閉
- 沒有右上 ✕ close 按鈕
- Generate 結果直接覆寫 System Prompt，無 preview / undo

**驗收**：
- [ ] Escape 鍵關閉 modal
- [ ] 點 backdrop 關閉 modal（textarea / dialog 內點擊不關）
- [ ] Top-right ✕ 按鈕
- [ ] 產生後不立刻寫入：顯示 preview（新 prompt 內容 + 簡易 diff 提示「此操作將覆寫現有 X 字 system prompt」），讓使用者按「Replace」確認，或「Cancel」放棄
- [ ] 使用 lucide `<Sparkles>` 取代 ✨ emoji（title 與 button 同步）
- [ ] 維持現有 streaming-less 行為（保留 SSE 升級給 Sprint C）

---

### A2. Profile Editor Header — chip 真實化 + 排版升級
**檔案**：`frontend/components/admin/profile-editor-header.tsx`

**問題**：
- Chips 寫死 "Realtime · Gemini Live · Deepgram STT"，與 profile config 無關（profile YAML 也沒 mode 欄位，stack 由 deployment-level env 決定）
- `<h1>` 是 text-base（16px）+ font-semibold，視覺重量不夠
- 返回鈕是 `←` 純 ASCII 14×20，當作 typo
- Cmd+Enter 存檔捷徑無視覺提示

**驗收**：
- [ ] 移除 "Realtime · Gemini Live · Deepgram STT" 寫死 chips；改成 1 個 chip + tooltip：
  - Chip：`Stack: deployment-defined` 或顯示語言 + 一個 info icon
  - tooltip 文字：「Stack（pipeline / realtime / LLM / STT / TTS）由 AGENT_AGENT_MODE 等部署 env 決定，profile 層級不可調」
  - 保留 language chip
- [ ] 返回鈕改用 lucide `<ArrowLeft size={18} />`，padding 包到 32×32 點擊區，加 `aria-label="返回 Profiles 列表"`
- [ ] `<h1>` 升級到 `text-lg font-semibold`（18px）或 `text-xl`
- [ ] Save 按鈕旁加 kbd 提示 `⌘⏎`（用 `<kbd>` 小標籤，淡灰色，hover 才顯示也可）
- [ ] 確保 768px 寬度時 chip 不換行斷字（`whitespace-nowrap`）

---

### A3. Prompt Editor — CM 主題協調 + Welcome 釐清
**檔案**：`frontend/components/admin/prompt-editor.tsx`

**問題**：
- CodeMirror oneDark 配淺色頁面，深色塊孤島
- Welcome Message + Welcome Instructions 兩欄並列，看起來像「都要填」，實際是 pipeline / realtime 互斥
- Generate 按鈕用 ✨ emoji
- 沒有 char count

**驗收**：
- [ ] 改用 CodeMirror light 主題（保留 markdown syntax highlight）：安裝 `@uiw/codemirror-theme-github` 或手寫 light theme（淺灰 gutter、黑字、藍色 keyword）
- [ ] Welcome Message 與 Welcome Instructions 加 helper text：
  - Welcome Message label 後：`(pipeline TTS 模式使用 — 逐字朗讀)`
  - Welcome Instructions label 後：`(realtime 模式使用 — Gemini 自由生成)`
  - 在兩欄上方加一行說明：「兩種模式只用一個欄位；建議依部署模式擇一填寫」
- [ ] Generate 按鈕：`✨ Generate` → lucide `<Sparkles size={14} />` + `Generate`
- [ ] System Prompt 編輯器底部加 stats row：`{N} chars · ~{N/4} tokens`（簡單 client-side 估算）
- [ ] CM line numbers 字級至少 12px

---

## Sprint B — Polish（GA 後可做）

| ID | 內容 | 檔案 |
|----|------|------|
| B1 | Try 按鈕 dirty 時改 modal confirm「未儲存，要先儲存後再 Try 嗎？」(取代 toast.error + disabled) | `profile-editor-header.tsx` + `use-profile-form.ts` |
| B2 | Flow Overview 最小高度 300px + 「展開全螢幕」按鈕 | `app/admin/(authenticated)/profiles/[id]/v2/page.tsx` (RightPanel) |
| B3 | "Collapse sidebar" 按鈕收合後文字改 "Expand" | `components/admin/sidebar.tsx` |
| B4 | 字級全域 floor 12px（移除 `text-[10px]` / `text-[11px]`） | header + collapsible-section |
| B5 | 觸控目標：Generate / + Add / ✕ / Inline-Tool call toggle 補到 32px | 多檔 |
| B6 | Sonner success toast 從 "Saved." 升級成「✓ Profile 已儲存」+ 短暫醒目樣式 | `use-profile-form.ts` |

---

## Sprint C — 加值（後話）

- C1：Generate prompt SSE streaming（Gemini Flash Lite 支援 stream）
- C2：Tablet（768px）響應式：右 panel 變抽屜
- C3：Generate「在現有 prompt 上補強」迭代模式
- C4：Token 估算改用 `gpt-tokenizer`（更準）
- C5：Section 折疊動畫（framer-motion 已裝？查）

---

## 不做（明確排除）

- ❌ Mobile（<640px）響應式：admin 內部用，桌面為主
- ❌ Profile schema 加 `mode` 欄位：mode 是 deployment-level，加進 profile 會增加 SIP / Cloud agent 邏輯複雜度（CLAUDE.md 已說明 SIP dispatch 限制）
- ❌ 換掉 Public Sans / 整體配色：不在 review 範圍

---

## 分派紀錄

| Sprint | Item | Agent | Status |
|--------|------|-------|--------|
| A | A1 GeneratePromptModal | A | dispatched |
| A | A2 Header | B | dispatched |
| A | A3 Prompt Editor | C | dispatched |
