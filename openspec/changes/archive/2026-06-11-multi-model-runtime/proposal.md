## Why

模型 provider / 端點目前散落並半寫死在 `agent.py`：realtime 模式的 Gemini Live 模型與聲音靠 `GOOGLE_REALTIME_MODEL` / `GOOGLE_REALTIME_VOICE` env 控制，pipeline 模式的 LLM / STT / TTS 則是寫死的 `FallbackAdapter` 清單。Profile（YAML / DB config）完全沒有模型欄位——換模型必須改 code 或動 deploy secret，無法 per-profile 切換。

我們剛實測用 managed graph 平台（Pathors）跑電梯 agent，卡在平台後端的模型 bug（`gpt-5.4` + reasoning_effort 被送錯 endpoint 直接 400），完全無法控制底層。這反證了 LiveKit「自控 runtime / 自選模型」的價值。本提案把多 provider 模型選擇與 pipeline 模式做成一等公民，效仿 Dograh 的 BYOK 多供應商策略（多 LLM / STT / TTS），讓 provider、模型、endpoint 都能 per-profile 或 per-deployment pin 住、自由替換。

## What Changes

- 新增 **provider 抽象層**（`agents/runtime/providers.py`）：以宣告式 spec（`{provider, model, options}`）解析出 LiveKit `llm.LLM` / `stt.STT` / `tts.TTS` 實例，支援 LiveKit Inference gateway 與多家直連 SDK（Google / OpenAI / Deepgram / Cartesia / ElevenLabs…），並提供 fallback chain 組裝。
- Profile schema 新增可選的 **`models` 區塊**：宣告 `mode`（pipeline / realtime）、LLM / STT / TTS provider+model+options、realtime 的 model/voice/thinking。未宣告時 fallback 到現有寫死預設（**非破壞性**）。
- Pipeline 模式升格為一等公民：`agent.py` 從 profile `models` 區塊建 session，而非寫死清單；強化 fallback 與 per-provider 設定。
- **保留並尊重 `TextInputRealtimeModel` 延遲規避設計**：realtime 模式的 LLM 仍只能是封裝後的 Gemini Live；多 provider 選擇套用在 STT（文字輸入來源）與 pipeline LLM/STT/TTS，不破壞「攔 push_audio → Deepgram STT → 文字餵 Gemini」信號流。
- **Cost 計費擴充**：`db/cost.py` 的 LLM/STT/TTS rate table 由 profile 選定的實際 model 驅動，新增 provider/model 的費率與 unknown-model 的 `incomplete` 標記策略。
- **設定流貫通**：定義 model spec 如何從 profile/deployment 流入 runtime，並處理既有的 multi-process 陷阱（child process 靠 env / profile config，不靠 `sys.argv`）與 SIP 無 metadata 限制。

## Capabilities

### New Capabilities
- `model-provider-runtime`: runtime 對 LLM / STT / TTS 多 provider 的解析與選擇——provider 抽象、model spec 結構、fallback chain 組裝、Inference 與直連 SDK 並存、realtime 模式對 `TextInputRealtimeModel` 的相容約束。
- `profile-model-config`: profile / deployment 層的模型設定 schema——`models` 區塊欄位、預設與 fallback 行為、設定如何流入 runtime（含 multi-process 與 SIP 限制下的解析優先序）。
- `multi-model-cost`: 多模型下的 cost 計費——rate table 由實際選定 model 驅動、新 provider/model 費率擴充、pipeline 與 realtime 兩條路徑的計費正確性與 unknown-model 處理。

### Modified Capabilities
<!-- openspec/specs/ 目前為空，無既有 capability，全部列為新增 -->

## Impact

- **Code**：`agents/agent.py`（session 組裝改讀 profile models）、新增 `agents/runtime/providers.py`、`agents/agent_factory.py`（傳遞 models 設定）、`agents/db/cost.py`（rate 驅動）、`agents/api/schemas.py` 與 `routes_profiles.py`（config 為 free-form dict，schema 不需 migration，但驗證需擴充）、`agents/api/routes_test.py`（Try button child_env 已注入 profile，需確認 models 設定隨 profile config 帶入）。
- **Profiles**：`agents/profiles/*.yaml` 新增可選 `models` 區塊；`example.yaml` 補欄位說明。
- **設定 / 部署**：新增可選 env（如各 provider API key）；deploy secret 仍以 `AGENT_PROFILE` 為主，模型選擇下沉到 profile config。
- **Dependencies**：可能新增 LiveKit plugin（`livekit-plugins-openai` / `-cartesia` / `-elevenlabs` 等，視支援的直連 provider 而定）。
- **Tests**：`agents/tests/` 需新增 provider 解析、fallback、cost 多模型測試；既有 `test_agent_system.py` 若觸及 session 組裝需同步。
- **Out of scope**：前端 graph 編輯器 UX、graph node/edge 資料模型與視覺化（由 graph-agent-builder 提案負責）。
