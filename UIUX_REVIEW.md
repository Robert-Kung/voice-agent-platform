# Profile 設定頁面 UI/UX Review

**日期**：2026-04-20
**範圍**：`/admin/profiles`（list）、`/admin/profiles/[id]`（detail / edit）、`/admin/profiles/new`
**測試方式**：Playwright + 1440×900 viewport，搭配原始碼 review

---

## 結論摘要

目前 profile 設定頁面以「工程師工具」的形式實作 —— 手刻 JSON、原生 `prompt()` / `confirm()`、無欄位驗證。對熟悉 schema 的開發者堪用，對非工程角色（客服 lead、PM）門檻過高，且容易在 production 因 typo 造成 agent crash。

下方依優先序列出 13 項問題與改善建議，**P0 為阻塞性問題**，**P1 為一致性與可用性**，**P2 為細節打磨**。

---

## 🔴 P0 — 嚴重影響使用者體驗

### 1. 用 `prompt()` 輸入 profile name
- **位置**：[frontend/app/admin/profiles/[id]/page.tsx:58](frontend/app/admin/profiles/[id]/page.tsx#L58)
- **問題**：建立新 profile 時跳出瀏覽器原生 `prompt()`，無法驗證格式 / 提示衝突 / 樣式化，行動裝置體驗差。
- **建議**：把 `name` 提升為表單第一個欄位，加 pattern hint（`^[a-z][a-z0-9_]*$`）與 inline 驗證；`display_name` 改放第二欄。

### 2. 整個 config 是一坨 JSON textarea
- **位置**：[frontend/app/admin/profiles/[id]/page.tsx:115-122](frontend/app/admin/profiles/[id]/page.tsx#L115-L122)
- **問題**：[`profiles/dental_clinic.yaml`](profiles/dental_clinic.yaml) 顯示 config 有結構化欄位（`agent_name` / `language` / `timezone` / `welcome_message` / `instructions` / `tools[]` / `human_operator_*`）。讓使用者手刻 JSON：
  - 易打錯逗號 / 引號，save 才報錯
  - 沒有 syntax highlight、line number
  - tools 是物件陣列，看不出有哪些可選工具
- **建議（依工程量遞增）**：
  - **MVP（採用）**：拆成多個欄位 — `Display Name` / `Agent Name` / `Language (select)` / `Timezone (select)` / `Welcome Message (textarea)` / `Instructions (textarea, 長)` / `Tools (multi-select checkbox)` / `Human Operator` 折疊區塊。多餘欄位放進「Advanced JSON」accordion。
  - **Better**：用 Monaco Editor / CodeMirror 取代 `<textarea>`，至少 JSON syntax highlight + 即時驗證。
  - **Best**：用 JSON Schema 自動產生表單（react-jsonschema-form）。

#### Monaco Editor vs JSON Schema → 自動表單

| 面向 | Monaco Editor | JSON Schema 自動表單 |
|------|--------------|----------------------|
| 定位 | 更好的 textarea | 不寫 JSON，改用表單 |
| 使用者看到 | 還是 JSON 文字，但有 highlight、錯誤紅線、補全 | 結構化欄位（input / select / array add 按鈕） |
| 學習門檻 | 仍需懂 JSON | 不需懂 JSON |
| 彈性 | 任何 JSON 都能編 | 受 schema 約束 |
| 適合 | 工程師、power user | 客服 / 業務 |
| Bundle size | 大（~2MB，需 lazy load） | 中（~200KB） |

**採用策略**：先 MVP 拆欄位 → 進階區塊用 Monaco → schema 穩定後再考慮自動表單。

### 3. `confirm()` / `alert()` 原生彈窗
- **位置**：[frontend/app/admin/profiles/page.tsx:29,34](frontend/app/admin/profiles/page.tsx#L29)
- **問題**：deactivate 用 `confirm()`，失敗用 `alert()`，會被瀏覽器擋住 / iframe 失效，視覺斷裂。
- **建議**：站內 modal + toast 取代。

---

## 🟡 P1 — 一致性與可用性

### 4. Tools 欄位過長把 row 撐爆
- **位置**：[frontend/app/admin/profiles/page.tsx:95-97](frontend/app/admin/profiles/page.tsx#L95)
- **問題**：`restaurant` 已 6 個 tools 一行就換行。
- **建議**：改用 `<chip>` 樣式，超過 N 個顯示「+3 more」hover 展開。

### 5. 沒有 search / filter / pagination
- **問題**：profiles 多了會崩。
- **建議**：至少加一個 name / display_name 的 search input。

### 6. 列表沒有「Edit」/「Try」按鈕，只有 Deactivate
- **問題**：使用者要點 name 連結才能 edit，要進 detail 頁才能看到 `/?profile=xxx` try link。
- **建議**：`Try` 直接放 row action。

### 7. 無 unsaved-changes 警告
- **位置**：[frontend/app/admin/profiles/[id]/page.tsx:51](frontend/app/admin/profiles/[id]/page.tsx#L51)
- **問題**：編輯一半切換頁面會直接遺失。
- **建議**：`beforeunload` listener + dirty state 比對。

### 8. 沒有 inactive profile 的 reactivate 按鈕
- **問題**：只能 deactivate，重新啟用得手動改 DB。
- **建議**：加 `Reactivate` action，或讓 deactivate 變成可逆。

### 9. `Deactivate` 紅色按鈕沒有 hover affordance
- **問題**：只有 underline，destructive action 應更明顯。
- **建議**：加 border / background hover。

---

## 🟢 P2 — 細節打磨

### 10. Profile detail 頁標題只有 `name`，沒顯示 `display_name`
- **位置**：[frontend/app/admin/profiles/[id]/page.tsx:98](frontend/app/admin/profiles/[id]/page.tsx#L98)
- **建議**：標題改為 `display_name`（大）+ `name` (mono, 小)。

### 11. Loading state 是純文字 "Loading..."
- **建議**：用 skeleton loader 或 spinner。

### 12. 表頭「Display Name」欄位太窄被 wrap 成兩行
- **建議**：給每欄合理的 width 或用 `whitespace-nowrap`。

### 13. 「Updated」日期用 `toLocaleString()`
- **問題**：不同 locale 看到不同格式。
- **建議**：統一 `YYYY-MM-DD HH:mm` 或顯示相對時間 + tooltip。

---

## 執行順序

1. **P0 #1 + #2 MVP（拆欄位 + 移除 prompt）** — UI/UX 收益最大
2. **P0 #3（站內 modal/toast）**
3. **P1 #4–#9** — 列表頁可用性
4. **P2 #10–#13** — 視覺打磨

---

## 截圖

- `profiles-list.png` — Profile 列表
- `profile-detail.png` — Profile 編輯頁
- `profile-new.png` — 新增 Profile 頁
- `dashboard.png` — Dashboard
