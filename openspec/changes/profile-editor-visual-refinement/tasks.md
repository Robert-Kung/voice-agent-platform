## 1. 共用樣式與基礎 (D3, D6)

- [x] 1.1 新增 type-scale 共用 className 常數（`editor-type-scale.ts`）
- [x] 1.2 抽出共用 DirtyBadge（`dirty-badge.tsx`），list 頁亦改用

## 2. 模型與語音全頁視圖 (D1, D2)

- [x] 2.1 `page.tsx`：`showStack`→`stackView`，移除 `StackSettingsModal`，header chip toggle
- [x] 2.2 `ProfileEditorLayout` 加 `fullWidth` slot + 「← 返回編輯」+ ESC（gate 在 AI-Generate / SaveConfirm modal 開啟時不誤觸發）
- [x] 2.3 `StackSettings` 內部邏輯一字未動，僅移出 modal 容器（`model-voice-view.tsx`）
- [~] 2.4 雙欄佈局採 **wrapper-level**（左說明欄｜右 StackSettings 控制欄）＋窄螢幕降單欄。**未做 per-segment（TTS/LLM/STT 各 `Model｜第二欄`）**——那需動 `RealtimePanel`/`PipelinePanel` 內部，與「不動 StackSettings 內部」約束衝突，故延後為 follow-up（見下方備註）
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

- [ ] 7.1 chip 導向全寬 Model & Voice 視圖；返回編輯後 dirty/未存草稿完整保留（view-swap 不 unmount）
- [ ] 7.2 Welcome 欄位依 `models.mode` 降權/互換、collapsed 欄位可展開且值不被清除
- [ ] 7.3 dirty badge 在 editor header 與 profiles list 視覺一致
- [ ] 7.4 對 5 個既有 profile（含 `elevator_repair_graph`、realtime/pipeline 各一）+ 新建流程做瀏覽器 QA：全頁視圖、雙欄、字級層級、header 分組
- [ ] 7.5 mobile/desktop 兩種寬度的 header 分組與雙欄降單欄檢查；ESC 優先序（上層有 modal 時不誤返回）
- [x] 7.6 `frontend` build 通過（next build 綠燈、無 type error）

> **§2.4 follow-up**：目前是 wrapper-level 雙欄；若要 prototype / reference 那種 per-segment（TTS/LLM/STT 各卡 `Model｜第二欄`），需在受控前提下重構 `RealtimePanel`/`PipelinePanel` 內部，以既有 28 個契約測試當護欄。建議獨立小 change 處理，不混進本次。
