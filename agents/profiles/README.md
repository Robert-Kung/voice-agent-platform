# Agent Profiles — 快速建立不同領域的語音客服

## 快速開始

```bash
# 預設使用 car_inspection profile
uv run agent.py console

# 指定 profile
uv run agent.py console --profile restaurant
uv run agent.py console --profile dental_clinic
uv run agent.py console -p car_inspection

# 透過環境變數指定
AGENT_PROFILE=restaurant uv run agent.py console
```

## 現有 Profiles

| Profile | 場域 | Tools |
|---------|------|-------|
| `car_inspection` | 車容坊加油站 | check_business_status, lookup_qa, check_weather, transfer_to_human |
| `dental_clinic` | 幸福牙醫診所 | check_business_status, lookup_qa, book_appointment, transfer_to_human |
| `restaurant` | 好食光餐廳 | check_business_status, lookup_qa, search_menu, calculate_price, transfer_to_human |

## 新增 Profile

1. 複製一個既有的 YAML 作為模板：

```bash
cp profiles/restaurant.yaml profiles/my_new_agent.yaml
```

2. 編輯 YAML，修改以下區塊：

### 基本資訊

```yaml
name: "我的店名"
agent_name: "voice-assistant-my-store"
language: "zh"
timezone: "Asia/Taipei"
```

### Tools 宣告（核心：每個 Agent 只掛載需要的 tools）

```yaml
tools:
  # 基本工具
  - name: get_current_datetime
  - name: transfer_to_human

  # 有營業時間需求才加
  - name: check_business_status

  # 有 FAQ 資料庫才加
  - name: lookup_qa

  # 需要菜單搜尋（餐廳、咖啡廳等）
  - name: search_menu
    config:
      categories:
        - name: "主餐"
          items:
            - name: "牛排"
              price: 580
              description: "紐約客牛排"

  # 需要天氣查詢（戶外活動、旅遊等）
  - name: check_weather
    config:
      location: "台北市"
      conditions:
        - condition: "晴天"
          temp_range: [25, 33]
          advice: "適合戶外活動"

  # 需要預約功能（診所、餐廳等）
  - name: book_appointment
    config:
      required_fields: ["姓名", "電話", "希望時段"]
      confirmation_message: "已記錄您的預約。"

  # 需要價格查詢
  - name: calculate_price
    config:
      price_rules:
        - name: "基本服務"
          base_price: 500
          description: "基本服務方案"
      currency: "TWD"
```

### 歡迎語

```yaml
welcome_message: |
  您好，歡迎致電 XX 店。
  查詢 A 服務請說一或按 1，
  需要重聽請說零或按 0。
```

### Agent Instructions（核心 Prompt）

```yaml
instructions: |
  你是「XX 店」的電話語音智慧客服 Agent，使用繁體中文回答。
  ...
```

### 服務定義（配合 check_business_status tool）

```yaml
services:
  my_service:
    always_open: false
    closed_days: [6]          # 0=Mon, 6=Sun
    schedule:
      weekday:
        start: "09:00"
        end: "18:00"
    hours_text:
      weekday: "平日上午 9 點至下午 6 點。"
      closed: "今日休息。"
```

### QA 資料庫（配合 lookup_qa tool）

```yaml
qa_data:
  - keywords: ["關鍵字1", "關鍵字2"]
    answer: "回答內容。"
```

### 模型 / 語音 / 語言堆疊（`models` 區塊，選填）

控制這個 Agent 用哪些 LLM / STT / TTS、聲音與語言。**整個區塊可省略** —— 省略時會套用內建編譯預設（與不寫 `models` 前的行為位元級相同），所以舊 profile 不受影響。也可只宣告其中一個 component，其餘自動 backfill 預設。

> Admin UI 的 **Stack 設定面板**（profile 編輯器右上角 Stack chip）就是在編輯這個區塊;下拉清單來自後端 catalog,且 catalog 內每個 model id 都經 LiveKit Inference gateway 實打驗證過(只列得出來的就跑得起來)。手填 YAML 時若填了清單外的 id,仍可用(free-text escape hatch),只是不保證 gateway 接受。

```yaml
models:
  mode: pipeline            # pipeline（STT+LLM+TTS 分離）| realtime（Gemini Live）

  # 每個 component 可給「單一 spec」或「spec 陣列」(陣列 = FallbackAdapter,主用第一個,失敗才退而求其次)
  llm:
    - { provider: google, model: gemini-3.1-flash-lite, via: inference }
    - { provider: openai, model: gpt-4.1-mini, via: inference }   # 第一個建不起來才用
  stt:
    - { provider: deepgram, model: nova-2, via: inference, language: zh-TW }
  tts:
    - { provider: cartesia, model: sonic-3, via: inference, language: zh,
        voice: "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc" }
    - { provider: elevenlabs, model: eleven_multilingual_v2, via: inference, language: zh }
```

每個 spec 的欄位:

| 欄位 | 說明 |
|------|------|
| `provider` / `model` | provider 名 + 該 provider 的 model id(`provider/model` 會組給 gateway) |
| `via` | `inference`(預設,走 LiveKit Inference gateway)或 `direct`(直連 provider plugin)。**`direct` 僅支援 `llm:google`(需 `GOOGLE_API_KEY`)與 `stt:deepgram`(需 `DEEPGRAM_API_KEY`)**;其他組合存檔會被擋 |
| `language` | BCP-47 語言碼(如 `zh-TW` / `zh` / `en`)。**advisory**:每個 model 有自己的支援清單(Admin UI 下拉),但不檔存檔,runtime 照樣送給 gateway。⚠️ Deepgram `nova-2-phonecall` / `*-medical` 等專用 model 只支援英文 |
| `voice` | **僅 TTS**。獨立的 voice id(不是編在 model id 裡),會以 `inference.TTS(voice=)` 傳入。每個 provider 有建議聲音清單,也可填自訂/複製的 voice id |
| `options` | 其餘傳給 component 的 kwargs(`provider`/`model`/`via`/`language`/`voice` 為保留字,不可放這裡) |

#### Realtime 模式

```yaml
models:
  mode: realtime
  realtime:
    model: gemini-2.5-flash-native-audio-preview-12-2025   # 僅允許 allowlist 內的 Gemini Live 變體
    voice: Kore                                            # Gemini Live 聲音
    stt: { provider: deepgram, model: nova-2, language: zh-TW }   # 文字輸入用的外部 STT
```

Realtime 是 `TextInputRealtimeModel`(語音 → Deepgram STT → 文字 → Gemini Live → 語音),用來規避 Gemini Live 直收音頻的 token 累積延遲。限制:

- **只允許 Gemini**(`google`/`gemini`)當 realtime LLM,且只有 allowlist 內、可計費的變體可選。`gemini-3.1-flash-live-preview` **不可用**(上游 SDK 對它停用 `generate_reply` 的文字注入,見 livekit/agents#5260)。
- **graph × realtime 互斥**:`editor_mode: graph` 的 profile 不能用 realtime(存檔回 422);graph 執行僅 pipeline。

#### 編譯預設(省略 `models` 時)

| component | 預設 |
|-----------|------|
| pipeline LLM | `google/gemini-3.1-flash-lite` →(fallback)`openai/gpt-4.1-mini` |
| pipeline STT | `deepgram/nova-2`(`zh-TW`) |
| pipeline TTS | `cartesia/sonic-3`(Jacqueline 聲音,`zh`)→(fallback)`elevenlabs/eleven_multilingual_v2` |
| realtime | `gemini-2.5-flash-native-audio-preview-12-2025`(聲音 `Kore`)+ `deepgram/nova-2` STT |

3. 執行測試：

```bash
uv run agent.py console --profile my_new_agent
```

## 架構說明

```
agent.py              ← 主程式（讀取 profile → 啟動 Agent）
agent_factory.py      ← Profile 載入 & 動態 Agent class 建立
agent_tools.py        ← Tool Registry（所有 tool 工廠）
profiles/
  ├── car_inspection.yaml
  ├── dental_clinic.yaml
  ├── restaurant.yaml
  └── README.md
```

### 模組化 Tool 系統

每個 tool 是獨立的工廠函式，定義在 `agent_tools.py`：

| Tool | 用途 | 需要的 YAML 區塊 |
|------|------|-------------------|
| `get_current_datetime` | 取得當前日期時間 | — |
| `check_business_status` | 判斷營業狀態 | `services` |
| `lookup_qa` | 關鍵字搜尋 FAQ | `qa_data` |
| `transfer_to_human` | 轉接真人服務 | `human_operator_*` |
| `check_weather` | 查詢天氣 | tool config `conditions` |
| `search_menu` | 搜尋菜單/目錄 | tool config `categories` |
| `book_appointment` | 預約登記 | tool config `required_fields` |
| `calculate_price` | 費用查詢 | tool config `price_rules` |

### 新增自訂 Tool

在 `agent_tools.py` 中：

```python
def make_my_custom_tool(profile: dict, config: dict):
    @function_tool
    async def my_custom_tool(self, param: str) -> dict:
        """Tool 的描述（LLM 會看到這段）"""
        # 你的邏輯
        return {"result": "..."}
    return my_custom_tool

# 加入 TOOL_REGISTRY
TOOL_REGISTRY["my_custom_tool"] = make_my_custom_tool
```

然後在 YAML profile 中宣告：

```yaml
tools:
  - name: my_custom_tool
    config:
      key: "value"
```
