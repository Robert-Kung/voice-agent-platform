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
