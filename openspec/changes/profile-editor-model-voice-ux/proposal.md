## Why

Graph 三部曲（`multi-model-runtime` / `graph-agent-builder` / `graph-runtime-executor`）已全數 archive，runtime 端能力齊備，但 **Profile Editor 前端沒跟上**：(1) 模型 / 語音選擇在 UI 上完全缺席——換模型只能改 deployment secret 或 YAML，profile 的 `models` 區塊 schema 已存在卻無編輯入口；(2) 「global 與 graph 是不是二選一」對使用者不清楚。本 change 把這層前端設計補齊，定位為「中度重設計」，不動已 archive 的 runtime 行為。

> **拆分（autoplan CEO F6）**：兩項純 hygiene（過期執行狀態文案、`tool_result_condition` validator parity）已切到獨立 change `graph-editor-execution-status-fix` 先 ship，不被本 feature 卡住。本 change 專注模型/語音 UI + global-as-base-layer IA。

## What Changes

- **模型選擇 UI（profile 級 + 引擎模式 tabs）**：新增 Stack 設定面板，以兩個 tab 呈現引擎模式——**Realtime (Speech-to-Speech)** 與 **Pipeline (BYOK：STT + TTS + LLM)**。每個 tab 暴露對應的 provider / model 欄位，並就地顯示限制提示：graph 執行僅 pipeline、realtime 下 node 切換被 Gemini Live 拒絕（1007）/ 靜默忽略、realtime LLM 只能是封裝後的 Gemini Live（保留 `TextInputRealtimeModel` 延遲規避）。讀寫 profile config 既有的 `models` 區塊，**不需 DB migration**。per-node 模型維持 schema 介面點，本 change 不做 UI。
- **語音設定面板**：voice picker（可搜尋、語言 / 性別 badge）、language、speed 等可調項；試聽（sample playback）標為延伸、非必做。
- **Global 為常駐底層、graph 選用疊加（心智模型釐清）**：UI 以**版面 affordance**（非純文案）呈現 global（`global_prompt` / persona / QA / hours / identity / tools + 模型/語音 stack）**永遠生效**，graph 只負責「流程分支」。簡單 agent 用 prompt 模式即可，需要多情境分支才開 graph——graph 疊在 global 之上，非二選一。解掉「global 的話不就不用 graph 了？」的疑問。
- **模型/語音 stack 落點**：從 header Stack summary chip 點開面板（非塞右側折疊區末端），避免最高風險設定被降到最低發現性的折疊槽。

## Capabilities

### New Capabilities
- `profile-editor-stack-ux`: profile 編輯器的模型 / 語音設定 UI 與 global-as-base-layer 資訊架構——引擎模式（realtime / pipeline）tab 切換（mode 變更需 confirm）、per-mode provider+model 欄位、compiled-default（標 inherited/pinned）顯示、模式限制與 graph×realtime 互斥的存檔前回饋、語音設定（realtime free-form / pipeline TTS）、互動狀態、model-list 單一真相（唯讀 endpoint）、以及 global 常駐底層 + graph 疊加層的版面呈現。讀寫既有 `models` 區塊。

## Impact

- **Frontend（主要）**：
  - `frontend/app/admin/(authenticated)/profiles/[id]/page.tsx`——header Stack chip → 點開模型/語音面板；global-as-base-layer 版面 affordance；`models.mode` 變更 confirm（比照 editor_mode）。
  - 新增模型 / 語音設定元件（引擎模式 tabs + voice 控制），由 Stack chip popover 開啟。
  - `frontend/hooks/use-profile-form.ts`——`KnownConfig` 已含 `models`；補模型 / 語音欄位的讀寫 actions、tab 切換 keep-but-don't-clear、`buildConfig` / `splitConfig` round-trip。
  - `frontend/components/admin/__tests__/`（vitest）——models round-trip、tab 切換保留、compiled-default helper、model-list 與後端常數的 contract 測試。
- **後端**：**硬性非目標——不改 runtime 行為、不動既有 `models` 驗證**。前端必須符合既有 `validate_models_block` 契約；若前端能產生現有 validator 會拒的形狀，那是前端 bug。唯一允許的後端新增是**一個唯讀 endpoint**（如 `GET /api/admin/model-defaults`），回傳編譯預設模型名 + 合法 provider/model/變體清單供前端消費——它不含任何 runtime 行為，且是「硬編兩份清單會漂移」的正解（見 design 風險）。`routes_profiles` 既有 graph×realtime 422 沿用。
- **資料模型**：profile `config` 為 free-form dict，新增 / 沿用 `models` 欄位**無需 migration**。
- **Out of scope**：變數 / 資料蒐集 UI（v1 已移除 `variable_keys`，留待後續 change）、per-node 模型 UI、版本 / rollback、test suites、AI 生成 graph 草稿、模型解析與 graph 執行的 runtime 行為（已 archive）。
