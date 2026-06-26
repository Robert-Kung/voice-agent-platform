## Why

Profile Editor v2 的 IA 選型（prompt-first split panel + global-as-base-layer）是對的，但視覺層沒跟上：整個編輯器幾乎壓在 `text-xs`/`text-[11px]`/`text-[10px]` 的扁平層級，讀起來像 config dump 而非設計過的產品；而 `profile-editor-stack-ux` 系列（archived `profile-editor-model-voice-ux` / `profile-model-catalog-runtime` / `profile-stack-language-selection`）三次迭代不斷往 Stack 面板加控制（engine tabs、provider/model 雙下拉、via 切換、voice picker、language matrix），全塞進一個 header chip 開的 `max-w-lg` center modal——pipeline 模式下內容溢出、主動作「完成」沉到 fold 以下。控制項數量已超出 modal 的容納上限，需要更大的可視空間。本 change 是**純前端視覺 / IA refinement**，把這層補齊，硬性非目標是不動 runtime 行為與既有 `models` 驗證契約。

## What Changes

- **模型 / 語音 Stack：center modal → 獨立全頁「模型與語音」視圖**。header 的 Stack chip 不再開 modal，改為導向一個全寬、雙欄佈局的 Model & Voice 視圖（執行模式雙卡 + TTS / LLM / STT 各段 `Model | 第二欄`，每段帶標題與一句說明）。讀寫的 `models` 區塊欄位、provider/model 列舉、via 切換、voice picker、language 控制**全部沿用**既有 `StackSettings` 邏輯與 catalog 契約，只換承載的容器與佈局。單一視圖內部分段，不再切子分頁。
- **Stack chip 升級為明確可編輯入口**：primary 色調 + settings cog icon + hover ring，跟旁邊純展示的語言 chip 拉開；點擊導向上述全頁視圖（取代「開 modal」），保留發現性。
- **字級補回中間層**：section 標題提到 `text-sm`(14px)/600、body 與輸入值 `text-sm`(13–14px)、`text-[10px]` 只留給 badge，建立 title→body→meta 三層，取代現在的扁平 micro 區間。
- **Header 兩個 mode 控制分組標示**：`editor_mode`（轉成 Graph / Prompt·Graph 切換）與 `models.mode`（引擎，現由 Stack chip 表示）加上極短分組 label（策略 / 引擎），讓正交但耦合（graph 需 pipeline）的兩軸在 resting state 就被區分，不只靠反應式 confirm modal 補救。
- **Welcome 欄位依當前引擎降權**：Welcome Message（pipeline 逐字朗讀）與 Welcome Instructions（realtime 生成）依當前 `models.mode` 把非生效那一個 collapse 起來並標示，不再等權並排。
- **Dirty 指示一致化**：editor header 的 amber 小圓點改為跟 profiles list 頁一致的 badge 樣式。

## Capabilities

### New Capabilities
- `profile-editor-presentation`: profile 編輯器的視覺層級與資訊呈現規則——type scale 三層（section 標題 / body / badge）、header `editor_mode` × `models.mode` 兩軸的分組視覺區分、Welcome 欄位依當前引擎模式的 active/inactive 呈現、以及未儲存（dirty）狀態在編輯器與列表頁的一致呈現。純前端表現層，不改任何讀寫的資料欄位。

### Modified Capabilities
- `profile-editor-stack-ux`: 「Stack reachable from header chip」的呈現契約改變——header chip 不再開 center modal，改導向獨立全頁、雙欄佈局的模型與語音視圖；chip 自身升級為帶可編輯 affordance 的入口。承載容器與佈局改變，但 engine-mode tabs、provider/model 列舉、inherited/pinned 標示、via 切換、voice picker、language 控制與所有 catalog / 驗證契約**不變**。

## Impact

- **Frontend（唯一範圍）**：
  - `frontend/app/admin/(authenticated)/profiles/[id]/page.tsx`——Stack chip 改為開啟全頁視圖（取代 `StackSettingsModal`）；header mode 控制分組；Welcome 區塊降權邏輯；dirty badge。
  - `frontend/components/admin/stack-settings.tsx`——`StackSettings` 內容元件**保留**，從 modal 容器抽出改放全頁視圖；TTS/LLM/STT 改雙欄分段佈局。
  - `frontend/components/admin/profile-editor-header.tsx`——chip affordance、mode 分組、dirty badge。
  - `frontend/components/admin/prompt-editor.tsx`——Welcome 欄位 active/inactive 呈現、字級。
  - `frontend/components/admin/profile-sections/*`、`collapsible-section.tsx`、`profile-editor-layout.tsx`——type scale 套用。
  - `frontend/components/admin/__tests__/`（vitest，**沿用 node-only harness**，見 design D7）——只放純資料轉換斷言：Stack 全頁視圖產出的 `models` 形狀 round-trip、既有契約測試綠燈。chip 導向 / Welcome 降權 / dirty 視覺等需 render 的行為由瀏覽器 QA 涵蓋，不引入 jsdom。
- **後端**：**無變更**。前端必須維持既有 `validate_models_block` 契約；不新增 endpoint、不動 model catalog。
- **資料模型**：無 migration。`models` 區塊讀寫欄位完全不變。
- **Out of scope**：runtime 行為（已 archive）、`models` 驗證規則、per-node 模型 UI、變數 / 資料蒐集 UI、版本 / rollback、整個編輯器遷移到 top-level tab 架構（本 change 只動模型/語音這一塊與既有 split-panel 內的視覺，tab 全面遷移留待後續）、dark-mode theming（沿用既有 theme tokens）。
