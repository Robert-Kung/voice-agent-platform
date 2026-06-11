## Context

`agents/agent.py` 目前把模型選擇半寫死：

- **Realtime 模式**（`AGENT_MODE=realtime`，預設）：`TextInputRealtimeModel`（封裝 `google.realtime.RealtimeModel`），模型/聲音靠 `GOOGLE_REALTIME_MODEL` / `GOOGLE_REALTIME_VOICE` env。STT 由 `_build_stt()` 在 `inference`（LiveKit Inference gateway）與 `deepgram`（直連）間切換，由 `AGENT_STT_PROVIDER` env 控制。
- **Pipeline 模式**：`AgentSession` 的 LLM / STT / TTS 是寫死的 `FallbackAdapter` 清單（`inference.LLM("google/gemini-3.1-flash-lite")` + `inference.LLM("openai/gpt-4.1-mini")`，STT/TTS 同理）。

Profile（`agents/profiles/*.yaml` 或 DB `config_json`，free-form dict）**完全沒有模型欄位**。換模型只能改 code 或動 deploy secret，無法 per-profile 切換。`db/cost.py` 的 rate table 靠對 metrics 回報的 model 名稱做 fuzzy match，realtime 路徑甚至寫死 `_REALTIME_DEFAULT` 與 Deepgram STT 費率。

關鍵約束（來自 CLAUDE.md，不可破壞）：

1. **TextInputRealtimeModel 延遲規避**：realtime 不是純 audio-in/out。Gemini Live 收原始音頻會讓 audio token 累積，延遲從 1–2s 漲到 20–30s。解法是攔 `push_audio`（no-op）+ `start_user_activity`（no-op），改由外部 STT 轉寫文字，經 `on_user_turn_completed → generate_reply(user_input=text)` 餵入 Gemini。**realtime 模式的 LLM 因此被綁死為「文字輸入的 Gemini Live」**，不能換成任意 provider 的 realtime model。
2. **multi-process 陷阱**：`entrypoint()` 在 SDK fork 的 child process 跑，不繼承 parent 的 `sys.argv`。設定必須走 env 或 profile config（child 會繼承 env、會重新 load profile）。
3. **SIP 限制**：Cloud dashboard 的 SIP dispatch rule 無 metadata 欄位，SIP 來電 profile 固定在 `AGENT_PROFILE` secret。模型選擇下沉到 profile config 後，SIP 來電自動拿到該 profile 的模型設定——這其實是改善（不再需要動 code）。

## Goals / Non-Goals

**Goals:**

- 一個宣告式 model spec（`{provider, model, options}`）→ LiveKit `llm.LLM` / `stt.STT` / `tts.TTS` 實例的解析層，支援 Inference gateway 與多家直連 SDK，並可組 fallback chain。
- Profile 新增可選 `models` 區塊，per-profile pin 模型 / endpoint；未宣告時行為與現在完全一致（非破壞）。
- Pipeline 模式從 profile 驅動，升格為一等公民。
- realtime 模式在不破壞 TextInputRealtimeModel 的前提下，仍能選 Gemini Live model/voice/thinking 與 STT provider。
- Cost 計費由實際選定 model 驅動，新增 provider/model 費率，unknown model 明確標 `incomplete`。

**Non-Goals:**

- 前端 graph 編輯器 UX、graph node/edge 資料模型與視覺化（graph-agent-builder 提案負責）。本提案只在 design 標註「與 graph-agent-builder 的介面點」。
- realtime 模式支援非 Gemini 的全雙工 realtime model（受 TextInputRealtimeModel 架構約束，暫不做）。
- 自動測速 / 自動選最佳 provider（未來事項）。
- Secrets / API key 管理 UI（key 仍走 env / deploy secret）。

## Decisions

### D1：宣告式 model spec + resolver registry

Model spec 是 plain dict，序列化進 profile config：

```yaml
models:
  mode: pipeline          # pipeline | realtime；省略時 fallback 到 AGENT_MODE env
  llm:
    - provider: google     # 第一個是主選，其餘為 fallback chain
      model: gemini-3.1-flash-lite
      via: inference        # inference（gateway）| direct（SDK + API key）
      options: { temperature: 0.7 }
    - provider: openai
      model: gpt-4.1-mini
      via: inference
  stt:
    - provider: deepgram
      model: nova-2
      via: inference        # 直連時 via: direct，用 DEEPGRAM_API_KEY
      language: zh-TW
  tts:
    - provider: cartesia
      model: sonic-3:9626c31c-...
      language: zh
  realtime:                 # mode=realtime 時使用
    model: gemini-2.5-flash-native-audio-preview-12-2025
    voice: Kore
    thinking_budget: 0
    stt: { provider: deepgram, model: nova-2, via: direct, language: zh-TW }
```

`agents/runtime/providers.py` 提供（**review 定案：輕量版，不上完整 registry**）：

- `build_llm(specs) / build_stt(specs) / build_tts(specs)`：單一 spec → 實例；多個 spec → 包進對應的 `FallbackAdapter`。每個 build 內部分流：
  - `via: inference`（預設）→ gateway passthrough，`inference.LLM/STT/TTS(f"{provider}/{model}", ...)`，**不需任何 provider 專屬 plugin**。
  - `via: direct` → 只特例兩條已實際需要的路徑：`deepgram`（Try button STT，等同既有 `_build_stt()`）與 `google` realtime（見 D3）。其餘 `direct` 組合 → fail loud。
- `KNOWN_DIRECT_PROVIDERS`：純字串常數集合（`{"deepgram", "google"}`），**不 import 任何 plugin 工廠**，給 schemas.py 驗證 enum 用（解 import-coupling，見 D6）。
- `resolve_session_components(profile, mode, env)`：把 profile `models` 區塊解析成 `AgentSession` 元件，缺欄位回填現有預設；回傳值**同時帶出 resolved 主模型名稱**（給 cost 用，見 D5）。

**為什麼輕量版而非完整 `(kind,provider,via)` registry？**（review 與 outside voice 定案）完整 registry 的唯一強理由是 graph-agent-builder（OQ4）的 per-node 選模型，但該介面尚未定案——先建等於 speculative generality，且每個 `direct` provider 都要裝對應 plugin（image 膨脹）。`via: inference` 對已在用的 5 家本來就只是 model 字串進 `inference.*`，不需 registry。`direct` 真正需要的只有 deepgram（Try button，已存在）與 google realtime。等 OQ4 介面定案、真的要 per-node 任意 provider 時再升級成 registry，`build_*` 的簽名不變，屆時是內部重構。

**Alternatives considered**：(a) 直接存 LiveKit plugin 物件——不可序列化，否決。(b) 一次上完整 registry——speculative generality + plugin 膨脹，延後到 OQ4。(c) 只暴露 Inference gateway 字串、完全不做 direct——會拿掉 Try button 既有的 deepgram direct 與 realtime 的 google direct，否決。

### D2：`via` 區分 Inference gateway 與直連 SDK

每個 spec 帶 `via`：`inference`（走 `livekit.agents.inference.LLM/STT/TTS`，Cloud 部署用，享 gateway fallback / 計費）或 `direct`（走 `livekit.plugins.<provider>` + 該 provider 的 API key env，本機 / pin endpoint 用）。預設 `via: inference`，與現狀一致。

這把現有 `AGENT_STT_PROVIDER`（inference/deepgram）一般化：Try button 的 `routes_test.py` 注入的 `AGENT_STT_PROVIDER=deepgram` 仍可作為**全域 override**（強制 STT 走 direct，省 free-plan concurrency quota），優先序高於 profile spec 的 `via`。保留此 env 不破壞既有 Try button 行為。

### D3：realtime 模式的約束邊界

`mode=realtime` 時：

- **LLM 永遠是 `TextInputRealtimeModel`**（封裝 Gemini Live）。`models.realtime.model` / `voice` / `thinking_budget` 只挑 Gemini Live 變體與聲音，**不接受非 Gemini provider**。resolver 對 realtime LLM 不查 `PROVIDER_REGISTRY` 的 llm 區，而是專門建 `TextInputRealtimeModel`。若 profile 在 realtime 模式下指定了非 Gemini 的 realtime provider → 驗證時報錯（fail loud），而非默默降級。
- **STT 仍可多 provider**（`models.realtime.stt`）——它是文字輸入的來源，正是 TextInputRealtimeModel 架構的合法擴充點。
- `push_audio` / `start_user_activity` 的 no-op、`automatic_activity_detection.disabled=True`、`input_audio_transcription=None` 等延遲規避設定**由 resolver 強制套用，不開放 profile 覆寫**。

這條邊界是本提案最重要的保護：多 provider 自由度給 pipeline 全段 + realtime 的 STT，但 realtime 的 LLM 端被刻意鎖死，以保住延遲修復。

### D4：設定流入優先序

runtime 解析 profile 與模式的優先序（沿用既有，模型設定掛在 profile config 上隨之流動）：

1. profile 選擇：room metadata > dispatch metadata > CLI `--profile` > `AGENT_PROFILE` env（已存在於 `_get_runtime_profile_name`）。
2. 模型設定：profile config 的 `models` 區塊（DB 優先於 YAML，已存在於 `load_profile_with_id`）。
3. 全域 env override：`AGENT_MODE`（覆寫 `models.mode`）、`AGENT_STT_PROVIDER`（強制 STT via）。
4. 缺漏回填：現有寫死預設。

child process 因為重新 load profile + 繼承 env，自動拿到正確模型設定，**不需碰 `sys.argv`**——天然避開 multi-process 陷阱。SIP 來電固定 profile 但自動帶該 profile 的 `models`，反而比現狀更好。

**Wiring 修正（review Finding 2）**：現有 `AGENT_MODE` 是 module-global，在 import 時就讀掉（`agent.py:195`），且同時驅動 session 分支（`agent.py:308`）與 `create_agent_class(profile, mode=AGENT_MODE)`（`agent.py:279`）。要讓 `models.mode` per-profile 生效，`entrypoint()` 必須在 `load_profile_with_id` **之後**算出 effective mode（`models.mode` ⊕ `AGENT_MODE` env override），再把這個值同時餵給 session 分支與 `create_agent_class`，不能再用 module-global。

### D5：Cost 計費由選定 model 驅動（review 定案：記錄於 session row + 凍結）

**關鍵修正（outside voice P1，已驗證）**：`FallbackAdapter.model` 回傳字面字串 `"FallbackAdapter"`（`fallback_adapter.py:80-81`），不是底層模型名。所以一旦用 fallback chain（D1 的主目的），metrics 回報的 `llm_model` 就是 `"FallbackAdapter"`，`_match_llm_rate` 找不到 → 整個 session 被標 `incomplete=True`。**這也代表現狀的 pipeline cost 早就受影響**（`agent.py:361` 已在用 FallbackAdapter）。因此「靠 metrics 回報的 model 名稱」這條路對 chained session 根本不可行。

定案做法：

1. **resolver 回傳 resolved 主模型名稱**（pipeline 的 LLM/STT/TTS、realtime 的 Gemini 變體 + STT provider）。
2. **session 起始時把這些名稱記在 DB session row**（`session_store.create_session` 加欄位），不依賴 metrics 的模型名。**欄位形狀須可擴充（2026-06-10 graph review 補充）**：用 JSON list/segments 結構而非單一字串欄位——graph-runtime-executor 的 per-node 模型（OQ4）會讓單一 session 跨節點使用不同 LLM，「一 kind 一名稱」的形狀屆時必須重做；現有實作尚未 commit，現在改最便宜。
3. `compute_cost(summary, selected=...)` 用記錄的名稱查 rate table；真的拿不到才退回 fuzzy match。
4. realtime STT 費率改依記錄的 realtime STT provider 查 `STT_RATES`，刪掉重複的 `_REALTIME_STT_RATE_PER_MIN`（Finding 5）。realtime LLM 變體查 `REALTIME_RATES`，保留 default。
5. **凍結歷史成本**：`routes_sessions.py:49-71` 目前在 read time 重算 `compute_cost`——一旦 rate table 改動，舊 session 會用今天的費率重算、或變 incomplete。改為**讀取 session row 上已存的 cost**（`complete_session` 已寫入 `raw_report_json.cost`），read path 不再重算（outside voice P3）。

rate table 擴充欄位涵蓋新 provider/model；unknown model 一律標 `incomplete=True` 而非估錯。

**為什麼不重寫計費？** token 欄位映射與 pipeline/realtime 分流正確，核心改動是「模型名稱來源」從 metrics 改為 session-row 記錄 + read path 停止重算，仍是最小變動。

realtime STT 費率（`_REALTIME_STT_RATE_PER_MIN = 0.0043`，`cost.py:33`）目前與 `STT_RATES["deepgram"]`（`cost.py:60`，同樣 0.0043）重複。D5 一併處理：realtime 路徑改為依 profile 的 realtime STT provider 查 `STT_RATES`，刪掉重複的寫死常數（review Finding 5）。

### D6：壞 spec 的處理策略（review Finding 1，OQ2 定案）

採「**存檔驗證 + 啟動硬擋 + FallbackAdapter 接住**」，**全程不偷偷換模型**：

1. **存檔時（admin UI）**：`schemas.py` 以 hand-written Pydantic schema 驗證 `models` 區塊形狀。**（2026-06-10 graph review 同步修正：與 D1 lite 版對齊，registry 已不存在）** provider enum **只約束 `via: direct`**，由 `KNOWN_DIRECT_PROVIDERS` 字串常數衍生；`via: inference` 是刻意開放的 gateway passthrough 字串（`provider/model` 直送 gateway），**不設 enum**——否則 gateway 的彈性被默默閹割。形狀錯誤回 422，壞設定進不了正式環境。
2. **啟動時**：resolver 對不支援的 `via: direct` 組合 **fail loud**（raise），不回填預設；`via: inference` 的未知 provider/model 由 gateway 在接通時回錯，落入第 3 層。
3. **執行時**：模型名稱合法但 provider 接通回錯（如 `gpt-5.4` + reasoning_effort → 400）由既有 `FallbackAdapter` 鏈換下一個 spec 吸收。

**注意邊界**：存檔驗證只能擋「形狀 / 未知 provider」錯誤，**擋不掉 provider 接通才回的 runtime 錯誤**（gpt-5.4/400 屬此類）——那一層唯一的安全網是 FallbackAdapter。

**FallbackAdapter 的真實限制（outside voice P1b，已驗證）**：它**不是**萬能網。
- 只在 chat turn 真的生成時才 failover（不是 `session.start()`），第一次 failover 會吃掉 `attempt_timeout`（預設 5s）的 dead-air——語音通話聽得到。
- `retry_on_chunk_sent=False`（預設）：模型已吐 chunk 後才錯 → 不重試，直接 raise，該 turn 死。
- `max_retry_per_llm=0`（預設）：單一 spec（D1 明確產生 bare component、無 adapter）**完全沒有 failover**。

所以「多 provider fallback chain 在會用到新模型的 profile 上不是選配，是必要」這句仍成立，但要在 example.yaml / 文件明寫：**pin 單一未驗證模型 = 無安全網**；要安全就配至少一個 fallback spec，且接受首次 failover 有 ~5s 延遲。為什麼不選 pipeline 默默回填預設？因為「指定 X 卻偷跑 Y + cost 用 Y 費率」是 silent failure，違反 explicit > clever，正是 Pathors「無法控制底層」的同類問題。

**realtime 的特別 footgun（outside voice P3）**：realtime 只有單一 `TextInputRealtimeModel`，**沒有 FallbackAdapter**，而 3.1-live 已知壞（1007，`agent.py:319`）。provider-level enum（`google`）擋不掉 pin 到壞變體。因此 `models.realtime.model` 不能是自由字串——需要一份 **Gemini Live 變體 allowlist**（驗證時檢查），不只驗 provider。

## Risks / Trade-offs

- [新增直連 provider 需新 LiveKit plugin 依賴，膨脹 image] → `via: direct` 的 provider 才需裝對應 plugin；首版只納入已在用的（google/deepgram/cartesia/elevenlabs/openai），其餘列為後續。
- [realtime LLM 鎖死 Gemini，使用者可能期待換 provider] → design 明確標示為架構約束（D3），驗證時 fail loud 並在 example.yaml 註明；未來若 plugin 改用 `send_realtime_input` 可重新評估。
- [profile 寫錯 model 名 → runtime build 失敗 → session 起不來] → resolver 對未知 provider/model fail loud（log + 回填預設或拒絕啟動，二擇一見開放問題 OQ2）；admin UI 端的下拉選單（graph-agent-builder 介面點）可進一步防呆。
- [Cost rate table 跟不上模型迭代] → unknown model 標 `incomplete`，UI 顯示「費率未知」而非錯誤金額；rate table 集中一處方便更新。
- [`AGENT_STT_PROVIDER` 全域 override 與 profile spec 衝突] → 明確定義 env override 優先（D2），並在 spec 寫成 scenario 測試。

## Migration Plan

1. 新增 `runtime/providers.py` + 測試，不接線。
2. `agent.py` 改用 `resolve_session_components`，無 `models` 區塊時回填現有預設——既有 5 個 profile 行為不變（回歸測試驗證）。
3. `db/cost.py` 接 profile 驅動 rate，保留 fuzzy fallback。
4. 挑一個 profile（如 `restaurant`）加 `models` 區塊做 pipeline 端到端驗證；realtime 維持預設驗證 TextInputRealtimeModel 未破壞。
5. `example.yaml` 補 `models` 說明。

**Rollback**：移除 profile 的 `models` 區塊即回到寫死預設；`runtime/providers.py` 的回填邏輯保證空 spec == 現狀。

## Open Questions

- **OQ1（定案：v1 = 已在用的 5 家）**：首版直連 provider 只納入 google / deepgram / cartesia / elevenlabs / openai，其餘走 Inference gateway，按需再擴充 registry。不一次列 Dograh 等級全清單。
- **OQ2（定案：見 D6）**：採存檔驗證 + 啟動硬擋 + FallbackAdapter，全程不偷偷換模型。取代原本的「pipeline 回填預設」建議。
- **OQ3（定案：純 per-profile + env override）**：不做 deployment 層級全域模型預設，列入 Non-Goals。需要時再加。
- **OQ4（與 graph-agent-builder 的介面點）**：graph 若要 per-node 選模型，node config 應內嵌相同的 model spec 結構，呼叫同一個 `resolve_session_components` / `build_llm`。本提案的 resolver 簽名需預留 graph 執行器可注入的彈性（spec 來源不限 profile）。此介面細節由 graph-agent-builder 提案定案。
- **OQ5（定案：單一 default + 可擴充表）**：realtime cost 暫不 per-Gemini-變體拆分；rate table 預留擴充欄位，未來 3.x 上線再加 key。
