## Context

現況 profile 編輯器是單一 page（`profiles/[id]/page.tsx`）內的 split-panel：`useProfileForm` hook 持有整份草稿與 dirty 狀態，`ProfileEditorLayout` 排中央 prompt + 右側折疊面板，模型/語音設定由 header Stack chip 開一個 `StackSettingsModal`（內含 `StackSettings` 元件）。三次 archived 迭代讓 `StackSettings` 控制項數量超出 `max-w-lg` modal 的容納上限。

約束：
- **不動 runtime / `models` 驗證**：前端產出的 `models` 形狀必須維持 `validate_models_block` 契約。
- **不可丟 dirty 狀態**：`useProfileForm` 的草稿存在 page 元件內；任何「換頁」方案若 unmount 此 page 會丟未存編輯。
- **沿用既有 catalog 契約**：`useModelCatalog` + shared fixture 的 provider/model/voice/language 來源不變。
- CLAUDE.md 記載 App Router prefetch / RSC 在此 admin 區會造成 redirect cache 問題，導航相關改動需謹慎。

## Goals / Non-Goals

**Goals:**
- 給模型/語音設定足夠的可視空間（全寬、雙欄），解掉 modal 擁擠與主動作沉底。
- 建立 type scale 三層，讓編輯器有視覺層級。
- 釐清 `editor_mode` × `models.mode` 兩軸、Welcome 雙欄、dirty 指示的呈現一致性。
- 全程零後端改動、零 migration、既有 `StackSettings` 行為與測試不回退。

**Non-Goals:**
- 不把整個編輯器遷移到 top-level tab 架構（圖 2~4 是別專案參考，本 change 只動模型/語音這塊與既有 split-panel 內視覺）。
- 不動 `models` 驗證、catalog、per-node 模型 UI、變數 UI、版本/rollback、dark-mode theming。

## Decisions

### D1：全頁模型與語音視圖用「page 內 view-swap」，不用 sub-route
在 `page.tsx` 以一個 `stackView: boolean` 狀態（取代現有 `showStack`），為 true 時 `ProfileEditorLayout` 在主內容區渲染**全寬** Model & Voice 視圖、隱藏 center/right split；為 false 回到編輯。
- **為何不用 sub-route（`/profiles/[id]/models`）**：sub-route 會 unmount 持有草稿的 page、丟 dirty 狀態，且觸及 CLAUDE.md 記載的 RSC prefetch/redirect 雷區。view-swap 讓 `useProfileForm` 持續掛載，dirty 安全，零導航風險。
- 代價：不可 deep-link / 無瀏覽器 back。以視圖內「← 返回編輯」按鈕 + ESC 返回；header Stack chip 作為 toggle。可 deep-link 留待日後 tab 遷移時一起做。
- **ESC 優先序**：現有 `StackSettingsModal`、AI-Generate modal、fullscreen flow overlay 都各自綁了 `keydown` Escape。view-swap 的 ESC-返回**只在沒有任何 modal/overlay 疊在上層時才生效**，不得搶走或雙觸發上層 overlay 的 ESC。

### D2：`StackSettings` 內容元件保留，只換容器 + 加佈局變體
`StackSettings`、`CatalogSpecField`、`TtsVoiceControl`、`LanguageControl`、`ViaToggle` 等**邏輯完全不動**（round-trip / 契約 / reset 行為都在這裡，動了就有回退風險）。改動限於：
- 拿掉 `StackSettingsModal` 的 modal chrome，把 `StackSettings` 放進全頁視圖容器。
- 在全頁容器套一層雙欄 grid：執行模式雙卡一列；TTS / LLM / STT 各為一段（標題 + 一句說明 + `Model | 第二欄` 雙欄）。窄螢幕降為單欄。
- 雙欄佈局由視圖層的 wrapper 負責；`CatalogSpecField` 仍輸出單一欄位群組，由 grid 排版。
- **為何**：把高風險的狀態邏輯與低風險的排版分離，最大化沿用、最小化測試回退面。

### D3：Type scale 以共用 className 常數收斂，避免漂移
新增一組共用樣式常數（如 `frontend/components/admin/profile-sections/styles.ts` 或就近 export）：`sectionTitle`（`text-sm font-semibold`）、`fieldLabel`（`text-xs`→`text-[13px]`）、`bodyText`（`text-sm`）、badge 維持 `text-[10px]`。套到 `collapsible-section`、`profile-sections/*`、`prompt-editor` label、stack 視圖。
- **為何常數而非逐處硬改**：避免三層尺寸在數十個 callsite 漂移；日後調一次到位。
- 只改 font-size / weight，**不動 spacing / padding**，降低版面位移風險。

### D4：Header 兩軸分組為兩個帶 label 的容器
`editor_mode` 控制（轉成 Graph / Prompt·Graph segmented）包進「策略」group，engine chip 包進「引擎」group，之間放一個輕量視覺關係提示（如 `→` 或分隔）。mobile 維持現有收合行為。
- **為何**：兩軸正交但耦合（graph 需 pipeline），resting state 的分組是教學；既有的反應式 confirm modal 仍是改動時的安全網，兩者互補。

### D5：Welcome 欄位依 `models.mode` active/inactive，但不清值、可展開
`prompt-editor` 讀 `form.modelsMode`：生效欄位（realtime→Instructions / pipeline→Message）正常顯示並標「生效中」；非生效那個收成 collapsed row（標示「X 模式才生效」），點擊可展開編輯。
- **為何可展開、不清值**：使用者可能在切模式前先寫好另一個欄位；collapse 是降權不是移除，值永遠保留 round-trip。

### D6：Dirty badge 抽共用元件
把 profiles list 頁的 dirty badge 樣式抽成共用小元件（或共用 className），editor header 與 list 共用，取代 header 的 amber 圓點。

### D7：沿用既有 node-only vitest harness，render 相關檢查走瀏覽器 QA
`frontend/vitest.config.ts` 已被前次 review（其 D7）刻意 pin 在 `environment: 'node'`，註解「Pure-function tests only (no jsdom, no component rendering)」，且 package.json **未裝** jsdom / `@testing-library/react`。本 change **沿用此決定、不引入 render harness**：
- 留在 vitest（node）：`models` 區塊 round-trip、`buildConfig`/`pruneModels`/`splitConfig`、catalog/語言 helper 等**純資料轉換**斷言。
- 移到瀏覽器 QA（task 7）：需要實際 render 的檢查——chip 導向全頁視圖、返回後 dirty/草稿保留、Welcome 依 mode 降權、dirty badge 視覺一致。
- **為何不裝 jsdom**：那會**反轉**前次 review 的明確決定，且為這次純視覺 refinement 引入新測試基礎設施，成本/風險不划算。既有 round-trip 測試在 node env、斷言純資料轉換，**不 mount `StackSettings`**，所以 D2 把元件 reparent 物理上不可能讓它們回退（見下方 Risks 修正）。

## Risks / Trade-offs

- **[StackSettings 重新 parent 導致既有測試回退]** → 風險其實被高估：既有 round-trip/契約測試在 node env、斷言純資料轉換、**不 mount `StackSettings`**，reparent 物理上動不到它們。真正的缺口是 **chip 導向 / Welcome 降權 / dirty badge 這些 render 相關行為目前無元件級覆蓋**——依 D7 由瀏覽器 QA（task 7）涵蓋，並跑既有 vitest（models round-trip、catalog 契約、語言 enable/disable）確認綠燈。
- **[view-swap 全頁蓋掉 prompt 造成迷向]** → 明確「← 返回編輯」+ ESC；chip 作 toggle；視圖標題清楚標示。
- **[type scale 掃描誤動 spacing 造成版面位移]** → 常數只含 font-size/weight；改動後對 5 個既有 profile + 新建流程做瀏覽器 QA 比對。
- **[全頁視圖未存編輯遺失]** → D1 view-swap 不 unmount page，`useProfileForm` 草稿續存；返回編輯狀態不變。
- **[Welcome collapsed 欄位發現性下降]** → collapsed row 帶可展開 affordance 與「為何未生效」說明。

## Migration Plan

純前端，無資料 migration。部署即生效（無 feature flag），rollback = revert commits。Ship 前 QA：5 個既有 profile（含 graph 的 `elevator_repair_graph`、realtime/pipeline 各一）+ 新建 profile，驗證 Stack 全頁視圖 round-trip、dirty、Welcome 隨 mode 切換、header 分組在 mobile/desktop 皆正常。

## Open Questions

- 全頁模型與語音視圖日後是否要升為可 deep-link 的 route？→ 與「整個編輯器遷移 tab 架構」一起評估，本 change 不做。
- Type scale 常數放置位置（共用 module vs 既有檔就近 export）→ 實作時依 import 圖最小化決定，不影響行為。
