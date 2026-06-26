## 1. 共用樣式與基礎 (D3, D6)

- [ ] 1.1 新增 type-scale 共用 className 常數（section 標題 `text-sm`/semibold、field label `text-[13px]`、body `text-sm`、badge 維持 `text-[10px]`），放在 admin 元件可共享處
- [ ] 1.2 抽出共用 DirtyBadge（或共用 className），對齊 profiles list 頁現有 dirty badge 樣式

## 2. 模型與語音全頁視圖 (D1, D2)

- [ ] 2.1 `page.tsx`：把 `showStack` 改為 `stackView` 狀態，移除 `StackSettingsModal`，由 header chip toggle
- [ ] 2.2 `ProfileEditorLayout`（或 page）：`stackView` 為 true 時於主內容區渲染全寬 Model & Voice 視圖、隱藏 center/right split；提供「← 返回編輯」+ ESC 返回。ESC-返回**只在沒有 modal/overlay 疊上層時生效**（不搶 AI-Generate modal / fullscreen flow overlay 的 ESC）
- [ ] 2.3 把 `StackSettings` 從 modal 容器抽出放進全頁視圖；**不動** `CatalogSpecField`/`TtsVoiceControl`/`LanguageControl`/`ViaToggle`/engine tabs 的內部邏輯
- [ ] 2.4 全頁視圖套雙欄佈局：執行模式雙卡一列；TTS / LLM / STT 各為一段（標題 + 一句說明 + `Model | 第二欄`），窄螢幕降單欄
- [ ] 2.5 驗證 `models` 區塊 round-trip 與既有 `validate_models_block` 契約不變（全頁視圖產出形狀與 modal 版一致）

## 3. Header chip 與兩軸分組 (D4, stack-ux chip affordance)

- [ ] 3.1 `profile-editor-header.tsx`：Stack chip 升級為可編輯 affordance（primary 色調 + settings cog + hover ring），點擊開全頁視圖
- [ ] 3.2 header 兩軸分組：`editor_mode` 控制包「策略」group、engine chip 包「引擎」group，加輕量關係提示；mobile 維持現有收合
- [ ] 3.3 確認既有 mode 切換 save-time confirm 行為不變（分組為純呈現）
- [ ] 3.4 header dirty 指示換成 1.2 的 DirtyBadge

## 4. Welcome 欄位降權 (D5)

- [ ] 4.1 `prompt-editor.tsx`：依 `form.modelsMode` 將非生效 welcome 欄位收成 collapsed row（標示「X 模式才生效」），生效欄位標「生效中」
- [ ] 4.2 collapsed 欄位可展開編輯、值永不清除（round-trip 保留），切 mode 時正確互換

## 5. Type scale 套用 (D3)

- [ ] 5.1 套用共用樣式到 `collapsible-section.tsx` 與 `profile-sections/*`（標題/label/body/badge 三層）
- [ ] 5.2 套用到 `prompt-editor` 的 label 與 Model & Voice 視圖
- [ ] 5.3 只改 font-size/weight，確認未動 spacing/padding 造成版面位移

## 6. 測試 — node-only vitest，純資料轉換 (D7)

> 不引入 jsdom / testing-library（沿用既有 `vitest.config.ts` 的 `environment: 'node'`）。本組只放不需 render 的斷言；需 render 的行為移至 §7 瀏覽器 QA。

- [ ] 6.1 Model & Voice 全頁視圖產出的 `models` 形狀與既有 modal 版一致（`buildConfig`/`pruneModels`/`splitConfig` round-trip 斷言）
- [ ] 6.2 既有 stack-ux 契約測試（catalog 列舉、語言 enable/disable、models round-trip）維持綠燈，確認 D2 reparent 未動到純函式

## 7. 瀏覽器 QA 與收尾（涵蓋 render 相關行為，D7）

- [ ] 7.1 chip 導向全寬 Model & Voice 視圖；返回編輯後 dirty/未存草稿完整保留（view-swap 不 unmount）
- [ ] 7.2 Welcome 欄位依 `models.mode` 降權/互換、collapsed 欄位可展開且值不被清除
- [ ] 7.3 dirty badge 在 editor header 與 profiles list 視覺一致
- [ ] 7.4 對 5 個既有 profile（含 `elevator_repair_graph`、realtime/pipeline 各一）+ 新建流程做瀏覽器 QA：全頁視圖、雙欄、字級層級、header 分組
- [ ] 7.5 mobile/desktop 兩種寬度的 header 分組與雙欄降單欄檢查；ESC 優先序（上層有 modal 時不誤返回）
- [ ] 7.6 `frontend` build 通過、無 console error
