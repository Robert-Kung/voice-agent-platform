## 1. 共用樣式與基礎 (D3, D6)

- [x] 1.1 新增 type-scale 共用 className 常數（`editor-type-scale.ts`）
- [x] 1.2 抽出共用 DirtyBadge（`dirty-badge.tsx`），list 頁亦改用

## 2. 模型與語音全頁視圖 (D1, D2)

- [x] 2.1 `page.tsx`：`showStack`→`stackView`，移除 `StackSettingsModal`，header chip toggle
- [x] 2.2 `ProfileEditorLayout` 加 `fullWidth` slot + 「← 返回編輯」+ ESC（gate 在 AI-Generate / SaveConfirm modal 開啟時不誤觸發）
- [x] 2.3 `StackSettings` 內部邏輯一字未動，僅移出 modal 容器（`model-voice-view.tsx`）
- [x] 2.4 雙欄佈局完成：wrapper-level（左說明欄｜右控制欄）**＋ per-segment**（`CatalogSpecField` 內 LLM/STT/TTS 各「左 provider+model｜右 via/voice/language」，無 secondary 的 LLM 退單欄）；窄螢幕(<sm)降單欄。僅動 JSX 排版，handler 全不變，28 契約測試綠
- [x] 2.5 `models` round-trip 與 modal 版一致（vitest 6.1 斷言 + build 綠燈）

## 3. Header chip 與兩軸分組 (D4, stack-ux chip affordance)

- [x] 3.1 Stack chip 可編輯 affordance（primary + settings cog + hover ring），開全頁視圖
- [x] 3.2 header 策略/引擎雙群組 + 關係提示；mobile 維持收合
- [x] 3.3 既有 mode 切換 save-time confirm 行為不變
- [x] 3.4 header dirty 換成共用 DirtyBadge

## 4. Welcome 欄位降權 (D5)

- [x] 4.1 `prompt-editor.tsx`：`WelcomeField` 依 `form.modelsMode` 降權非生效欄、標示生效中
- [x] 4.2 collapsed 欄位可展開、值不清除（行為待瀏覽器 QA 7.2 驗收）

## 5. Type scale 套用 (D3)

- [x] 5.1 套用到 `collapsible-section.tsx` 標題 + `profile-sections/{identity,handoff,qa}` field label
- [x] 5.2 套用到 `prompt-editor` label 與 Model & Voice 視圖
- [x] 5.3 只改 font-size/weight（版面位移待 QA 7.4 目視確認）

## 6. 測試 — node-only vitest，純資料轉換 (D7)

> 不引入 jsdom / testing-library（沿用既有 `vitest.config.ts` 的 `environment: 'node'`）。本組只放不需 render 的斷言；需 render 的行為移至 §7 瀏覽器 QA。

- [x] 6.1 Model & Voice round-trip 斷言（+3 tests，併入 feat 25-test 版 → 28）
- [x] 6.2 既有 stack-ux 契約測試維持綠燈（vitest 76 pass）

## 7. 瀏覽器 QA 與收尾（涵蓋 render 相關行為，D7）

- [x] 7.1 chip 導向全寬視圖（view-swap、URL 不變）；返回後 Save 變可按、prompt 草稿完整保留 ✓
- [x] 7.2 Welcome 依 `models.mode` 降權（realtime→Instructions 生效、Message 收合「已填內容」）；展開後原值完整保留 ✓
- [x] 7.3 dirty badge editor「● 未儲存」與 list「● dirty」同款 amber pill ✓
- [x] 7.4 dental_clinic(realtime) + elevator_repair_graph(graph/pipeline) QA：全寬視圖、雙欄、inherited/pinned badge、語言 picker 未回退、字級層級、策略/引擎分組 ✓
- [x] 7.5 ESC 由全寬視圖返回編輯 ✓；mobile(390) header 分組正確收合 ✓（註：engine chip 為 md+ only，mobile 無法經 chip 開 Model&Voice — pre-existing，非本次造成）
- [x] 7.6 `frontend` build 通過（next build 綠燈、無 type error）

> **§2.4 已完成 per-segment 雙欄**（受控重構 `CatalogSpecField` JSX 排版，handler 不變，28 契約測試 + tsc + build 綠、瀏覽器 QA 確認三段皆 `Model｜secondary` 雙欄、窄螢幕降單欄）。同批附帶修掉 language-selection 帶進來的 pre-existing 型別錯（`model-stack.test.ts` `buildConfig` 少參數）。
