> 過期文案 + `tool_result_condition` parity 已移至獨立 change `graph-editor-execution-status-fix`（先 ship）。本檔僅模型/語音 UI + global-as-base-layer IA。gate 決策：D-T1=加唯讀 endpoint、D-T2=header chip popover、D-T3=拆（已拆）、變數維持不做。

## 1. 表單狀態與資料來源

- [ ] 1.1 `useProfileForm`：補 `models` 區塊讀寫 actions（set mode / llm / stt / tts / realtime 子欄位）；`buildConfig` / `splitConfig` round-trip `models` 完整、`isDirty` 納入新欄位
- [ ] 1.2 引擎 tab 切換 **keep-but-don't-clear**：切到另一 mode 不清除前一 mode 的 `models` 子區塊；vitest round-trip（切過去再切回，realtime 與 stt/tts/llm 子區塊都保留）
- [ ] 1.3 **model-list / 預設單一真相（D-T1）**：實作唯讀 `GET /api/admin/model-defaults`，回傳編譯預設模型名 + 合法 provider/model/realtime 變體清單（來源對齊後端 `KNOWN_DIRECT_PROVIDERS` + realtime 變體 allowlist + pipeline 編譯預設）。此為唯一允許的後端新增（純唯讀、無 runtime 行為）
- [ ] 1.4 前端消費該 endpoint；compiled-default helper：`models` 缺欄位時顯示編譯預設（標 **inherited** vs **pinned**），**不**寫入 config；標注部署 env（`GOOGLE_REALTIME_*`）可覆蓋——顯示值非保證 runtime-effective

## 2. 模型選擇 UI（引擎模式 tabs）

- [ ] 2.1 Stack 設定元件：Realtime / Pipeline 兩 tab，選 tab 設 `models.mode`；Pipeline tab 顯示 STT/TTS/LLM provider+model selector，Realtime tab 顯示 realtime model/voice/thinking
- [ ] 2.2 **入口（D-T2）**：header Stack summary chip 點開該面板（popover/panel），非塞右側折疊區末端
- [ ] 2.3 Realtime 限制就地呈現：LLM 僅 Gemini Live 變體（封裝後）、known-dead 變體不可選、不提供非 Gemini realtime provider；inline 說明 `TextInputRealtimeModel` 延遲規避
- [ ] 2.4 `models.mode` 變更視為**策略變更**：存檔前 confirm（比照 editor_mode 既有 confirm modal），文案說明改的是 runtime 引擎（成本/延遲/graph 執行）

## 3. 語音設定

- [ ] 3.1 語音欄位精確對應：realtime→`models.realtime.voice`（v1 free-form 輸入，可帶 suggestions）、pipeline→`models.tts`（provider/model selector，voice 編在 model id）；round-trip 正確
- [ ] 3.2 **不**做 metadata catalog / 試聽（本 repo 無 voice catalog 來源，spec 不暗示有 metadata）；speed/language 不支援時 hide/disable

## 4. graph×realtime 互斥回饋

- [ ] 4.1 `editor_mode: graph` 且選 Realtime tab 時就地顯示 blocking-intent 警告（graph 僅 pipeline、存檔會被 422）；**不**前端硬擋存檔
- [ ] 4.2 後端回 422 時把錯誤就地呈現為「graph×realtime 互斥」（engine-mode 控制附近）、保留未存編輯
- [ ] 4.3 後端**硬性非目標**把關：不改 `validate_models_block` / runtime；前端必須符合既有契約（能被現有 validator 拒=前端 bug）。唯一後端新增是 1.3 唯讀 endpoint

## 5. Global-as-base-layer IA

- [ ] 5.1 用**版面 affordance**（常駐「global 適用全域」容器，或 graph canvas 包在「branching layer」框內）呈現 global 常駐底層、graph 為疊加分支層——非純文案
- [ ] 5.2 mode 切換處說明：prompt 模式（單一全域）適合單流程 agent，graph 在同一 global 上加多分支
- [ ] 5.3 global config（含模型/語音 stack）跨 prompt↔graph 轉換/還原不變；補測試

## 6. 互動狀態

- [ ] 6.1 realtime LLM 受限/disabled 可見態（非 Gemini 不提供、dead 變體不可選且有原因，非無故鎖死）
- [ ] 6.2 新欄位 dirty 態走既有 `isDirty`；若清單改 fetch 則補 loading / fetch-error 態（不靜默渲染空 picker）

## 7. 測試與驗證

- [ ] 7.1 vitest 全綠：models round-trip、tab 切換 keep-but-don't-clear、compiled-default helper、model-list 與後端常數 contract 測試（防漂移）、realtime 變體 ↔ cost rate 同步
- [ ] 7.2 `cd agents && uv run pytest tests/ -q` 全綠（僅新增唯讀 endpoint，既有 147+ 不受影響）
- [ ] 7.3 frontend build 通過
- [ ] 7.4 瀏覽器 QA：Stack chip 開面板；引擎 tab 切換寫對 `models.mode` 且非破壞；Realtime 限制生效；mode 變更 confirm；語音 round-trip；graph+realtime 存檔被 422 並就地呈現；global affordance 在兩模式可見；prompt↔graph 切換不回歸
- [ ] 7.5 `openspec validate profile-editor-model-voice-ux --strict` 通過
