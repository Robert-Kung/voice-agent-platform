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

## Sprint A — 必修（GA 前）✅ 完成

### A1. AI Generate Modal 關閉與覆寫保護 ✅
**檔案**：`frontend/app/admin/(authenticated)/profiles/[id]/v2/page.tsx`（`GeneratePromptModal` 元件）

- [x] Escape 鍵關閉 modal
- [x] 點 backdrop 關閉 modal（textarea / dialog 內點擊不關）
- [x] Top-right ✕ 按鈕
- [x] 產生後不立刻寫入：顯示 preview，讓使用者按「Replace」確認，或「重新產生」放棄
- [x] 使用 lucide `<Sparkles>` 取代 ✨ emoji
- [x] 維持現有 streaming-less 行為

---

### A2. Profile Editor Header — chip 真實化 + 排版升級 ✅
**檔案**：`frontend/components/admin/profile-editor-header.tsx`

- [x] 移除寫死 chips；改成 `Stack: deployment-defined` chip + info icon tooltip
- [x] 保留 language chip
- [x] 返回鈕改用 lucide `<ArrowLeft size={18} />`，加 `aria-label`
- [x] `<h1>` 升級到 `text-lg font-semibold`
- [x] Save 按鈕旁加 `<kbd>⌘⏎</kbd>` 提示
- [x] chip `whitespace-nowrap`

---

### A3. Prompt Editor — CM 主題協調 + Welcome 釐清 ✅
**檔案**：`frontend/components/admin/prompt-editor.tsx`

- [x] 改用 CodeMirror light 主題（`@uiw/codemirror-theme-github`）
- [x] Welcome Message / Welcome Instructions 加 helper text + 說明行
- [x] Generate 按鈕：lucide `<Sparkles size={14} />` + `Generate`
- [x] System Prompt 底部加 stats row：`{N} chars · ~{N/4} tokens`
- [x] CM line numbers 字級 12px

---

## Sprint B — Polish ✅ 完成

| ID | 內容 | 狀態 |
|----|------|------|
| B1 | Try 按鈕 dirty 時改 inline confirm popup + handleSaveAndTry | ✅ |
| B2 | Flow Overview 最小高度 300px + 全螢幕展開 overlay | ✅ |
| B3 | Sidebar toggle 收合後文字改 "Expand" | ✅ |
| B4 | 字級 floor 12px（`text-[10px]` → `text-xs`） | ✅ |
| B5 | 觸控目標 ✕ / + Add 補到 `min-h-8 min-w-8` (32px) | ✅ |
| B6 | Sonner toast 升級：`Profile 已儲存` + duration 3s | ✅ |

另修：
- ✅ Tools section defaultOpen race condition（builtinSelected async → sync rawBuiltinCount）
- ✅ Service Hours `hours_text` 物件型別改為可編輯 textarea（JSON 雙向）

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
| A | A1 GeneratePromptModal | A | ✅ done |
| A | A2 Header | B | ✅ done |
| A | A3 Prompt Editor | C | ✅ done |
| B | B1–B6 + bug fixes | parallel | ✅ done |
