# Operator Tool API — 骨架需求與建置指南

這份文件給「**另開一個對話 / repo 來建電梯報修 LINE API**」的新 session 用。
讀完這份文件即可開工，不需要 voice-agent-workshop 的完整 context。

---

## 1. 這支 API 在整個架構的角色

```
住戶 (打電話) ──┐
                ▼
         LiveKit Room
                ▼
         voice-agent-workshop (agent.py)
                │
                │  HTTP POST （Tier 3 tool call）
                ▼
         ★ 你要建的 API 在這裡 ★
                │
                ├──→ LINE push 通知維修人員
                ├──→ 寫工單到 DB
                └──→ 回 success + ETA 給 agent
```

Voice agent 平台（voice-agent-workshop）已經做完。它會用 profile 設定動態建一支
`@function_tool`，當 LLM 認為要回報故障時呼叫你這支 API。

---

## 2. Profile 端的合約（已存在）

Profile 在 `voice-agent-workshop/profiles/elevator_repair.yaml`，相關片段：

```yaml
tools:
  - name: report_elevator_failure
    endpoint: https://CHANGE_ME.example.com/elevator/report  # ← 你的 API URL
    method: POST
    auth_header: "Bearer ${ELEVATOR_API_KEY}"  # ← 你的 API key, 平台 ENV 注入
    timeout_seconds: 10
    parameters:
      - { name: building,       type: string, required: true,  description: 棟別 }
      - { name: elevator_id,    type: string, required: true,  description: 電梯編號 }
      - { name: symptom,        type: string, required: true,  description: 故障狀況 }
      - { name: contact_phone,  type: string, required: true,  description: 住戶聯絡電話 }
      - { name: caller_floor,   type: string, required: false, description: 住戶所在樓層 }
```

**你需要實作的：**
- `POST /elevator/report`
- 驗證 `Authorization: Bearer ${ELEVATOR_API_KEY}`
- 接收 JSON body 含上面 5 個參數
- 回傳格式（agent 期待的）：
  - 成功：`{"success": true, "ticket_id": "T-2026-0001", "eta_minutes": 30}`
  - 失敗：`{"success": false, "error": "原因"}` 或 4xx/5xx

---

## 3. 業務邏輯需求

### 3.1 收到 report 後要做的事
1. 產生 ticket_id（時序遞增 + 日期前綴，如 `T-2026-0001`）
2. 寫工單到 DB（建議 SQLite，可後續換 Postgres）— 至少存：
   - ticket_id, building, elevator_id, symptom, contact_phone, caller_floor
   - created_at, status (default: `open`)
3. 推 LINE 通知到維修人員群組（透過 LINE Messaging API push）
   - 訊息內容範例：
     ```
     🚨 電梯報修
     棟別: A 棟
     電梯: 1 號
     狀況: 不會動，按了沒反應
     聯絡: 0912-345-678 (住戶在 5 樓)
     工單: T-2026-0001
     ```
4. 回應 agent：成功 + ETA（先固定回 30 分鐘，未來可依時段或維修人員位置動態判斷）

### 3.2 額外建議的 endpoints（可選，看需求加）
- `GET /elevator/tickets/{ticket_id}` — 查工單狀態（給住戶後續詢問用）
- `POST /elevator/tickets/{ticket_id}/ack` — 維修人員確認接單（可由 LINE bot webhook 觸發）
- `GET /elevator/tickets?status=open` — 列出未處理工單（給管理介面用）

---

## 4. 技術選擇建議

| 項目 | 建議 | 理由 |
|---|---|---|
| 語言 | Python 3.11+ | 與 voice-agent 一致，未來抽共用較容易 |
| Framework | FastAPI | 自動 OpenAPI、Pydantic validation |
| LINE SDK | `line-bot-sdk` (官方 Python SDK) | 成熟、有型別 |
| DB | SQLite（dev）→ Postgres（prod） | 用 SQLAlchemy 寫 ORM 一次抽換 |
| Async | 全 async（`async def`） | LINE push 是 IO bound |
| 部署 | Docker + Render / Fly.io / 你自家 VPS | 要公網 HTTPS（agent 端 SSRF 擋私網） |

---

## 5. 建議目錄結構

```
elevator-tool-api/
├── pyproject.toml          uv 管 deps
├── main.py                 FastAPI app entry
├── api/
│   ├── __init__.py
│   ├── auth.py             Bearer token 驗證 dependency
│   ├── routes_elevator.py  /elevator/report 等 endpoints
│   └── schemas.py          Pydantic models（request / response）
├── services/
│   ├── __init__.py
│   ├── line_client.py      LINE Messaging API wrapper（未來可抽 shared/）
│   └── tickets.py          工單建立 / 查詢 / 狀態更新
├── db/
│   ├── __init__.py
│   ├── models.py           SQLAlchemy Ticket model
│   └── engine.py           Session factory
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_routes.py      mock LINE，驗 endpoint 正確性
│   └── test_tickets.py
├── Dockerfile
├── docker-compose.yml      app + sqlite volume
├── .env.example
├── .gitignore
└── README.md
```

---

## 6. 環境變數（.env.example）

```env
# LINE Messaging API（從 LINE Developers Console 拿）
LINE_CHANNEL_ACCESS_TOKEN=
LINE_CHANNEL_SECRET=
LINE_TARGET_GROUP_ID=          # 維修人員群組 ID（事先在 group 中加 bot 取得）

# 給 voice-agent-workshop 認證用
ELEVATOR_API_KEY=              # 與 voice-agent-workshop env 同值

# DB
DATABASE_URL=sqlite:///./tickets.db
# 或 postgres://user:pw@host:5432/elevator

# 服務
HOST=0.0.0.0
PORT=8090
LOG_LEVEL=INFO
```

對應 voice-agent-workshop 端要設：
- `ELEVATOR_API_KEY=同上` （`.env` 或 `lk agent secrets set`）
- profile 的 endpoint 改成 `https://你部署的網址/elevator/report`

---

## 7. 關鍵實作要點

### 7.1 Auth dependency
```python
# api/auth.py
from fastapi import Header, HTTPException
import os

def verify_api_key(authorization: str = Header(...)):
    expected = f"Bearer {os.environ['ELEVATOR_API_KEY']}"
    if authorization != expected:
        raise HTTPException(401, "invalid api key")
```

### 7.2 Endpoint
```python
# api/routes_elevator.py
@router.post("/report", dependencies=[Depends(verify_api_key)])
async def report(req: ReportRequest, db: Session = Depends(get_db)):
    ticket = await tickets.create(db, req)
    await line_client.push_to_group(format_message(ticket))
    return {"success": True, "ticket_id": ticket.id, "eta_minutes": 30}
```

### 7.3 LINE push（避免阻塞）
- 用 `httpx.AsyncClient` 打 LINE API
- 設 timeout（5s），失敗也別讓整個 request 失敗 — 工單已寫入 DB，LINE 推播失敗可重試
- 建議：寫一個簡單 retry queue（背景 task / cron）

### 7.4 一定要有的測試
- `test_auth.py`：missing / wrong / valid token
- `test_routes.py`：mock LINE client，驗 happy path 回 success + ticket_id
- `test_tickets.py`：DB 寫入正確、ticket_id 唯一、status 預設 open

---

## 8. 部署 checklist

- [ ] HTTPS（voice-agent SSRF 防護擋 http://）
- [ ] 公網可達（不能 localhost / 私網）
- [ ] `Authorization` header 強制檢查
- [ ] LINE channel token 不要 commit 進 repo
- [ ] DB volume 持久化（container 重建不丟工單）
- [ ] Health check `GET /health`
- [ ] 部署後手動 curl 一次：
  ```bash
  curl -X POST https://your-domain/elevator/report \
    -H "Authorization: Bearer $ELEVATOR_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"building":"A","elevator_id":"1","symptom":"test","contact_phone":"0912345678"}'
  ```

---

## 9. 上線後回 voice-agent-workshop 端要做

1. 編 `profiles/elevator_repair.yaml`（或在 admin UI 編 profile）：
   - endpoint URL 改成你的網址
2. 設 `ELEVATOR_API_KEY` env：
   - 本機：`.env` 加一行
   - LiveKit Cloud：`lk agent secrets set ELEVATOR_API_KEY=...`
3. 重啟 agent / 重新 deploy
4. 三端測試：
   - Console: `uv run agent.py console --profile elevator_repair`
   - WebRTC: admin UI 的 "Try" 按鈕
   - SIP: 撥真實電話進測試號碼

---

## 10. 給新對話的提示

新對話應該：
1. 讀這份文件
2. 確認需求理解（特別是 ticket_id 格式、LINE 訊息範本、ETA 邏輯）
3. 開新 repo `elevator-tool-api`，按 §5 的目錄結構搭骨架
4. 跑 minimal happy-path test 驗證可以收 / 可以推 LINE / 可以寫 DB
5. 部署到公網 HTTPS（建議 Render 免費方案先 POC）
6. 回到 voice-agent-workshop 改 profile endpoint，三端測試

**不要** 把這份 API 寫進 voice-agent-workshop。理由見 voice-agent-workshop 的 `CLAUDE.md`「Tool 架構決策」段落 — Tier 3 設計要求業務 API 跟平台分離。
