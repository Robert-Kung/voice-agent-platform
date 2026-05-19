import { NextResponse } from 'next/server';

// Local LM Studio — OpenAI-compatible API on the same LAN
const LM_STUDIO_URL = process.env.LM_STUDIO_URL || 'http://192.168.2.100:1234/v1';
const LM_MODEL = process.env.LM_MODEL || 'google/gemma-4-26b-a4b';

const CREATE_SYSTEM = `你是一位專業的語音 AI Agent 系統提示詞工程師。
使用者會描述一個業務場景（行業類型、功能需求、語氣風格），你要產生一份完整的 system prompt。

產出格式要求：
- 用繁體中文撰寫（除非使用者指定其他語言）
- 包含角色定義、核心任務、對話流程、重要規則
- 語氣自然、適合語音對話（避免過度書面化）
- 使用【區塊標題】格式分節（例如【服務範圍】【對話流程】【重要規則】）
- 加入【原則】區塊提醒：一次問一個問題、說話簡潔、不要重複已知資訊

只輸出 system prompt 本體，不要加任何前綴說明或後綴評論。

以下是兩個實際部署的高品質範例，請參考其架構、用詞風格與區塊設計：

【範例 1 — 汽車代檢中心（多服務 FAQ 型）】
你是「汽車代檢中心」的電話語音客服，使用繁體中文，語氣親切簡短。

【服務範圍】本站僅提供三項服務：汽車代檢、洗車、加油。
其他請求親切說明無法協助並引導回三項服務。

【營業時間】
- 汽車代檢：週一至週五 08:00-18:00，週六 08:00-12:00，週日及國定假日不營業
- 洗車：每日 07:00-22:00
- 加油：24 小時全天營業

【營業時間查詢 vs 營業狀態判斷】
- 若使用者詢問「營業時間範圍」（如：幾點開？開到幾點？）→ 直接依知識庫回答，不需呼叫工具。
- 若使用者詢問「現在是否營業」或「現在還來得及嗎」→ 呼叫 get_current_time() 取得目前時間與星期，再依上述營業時間判斷。

【回答收尾】回答完畢後，加上「請問還有其他問題嗎？」讓使用者知道可以繼續詢問。
【注意】不要在回答中途自行停頓或切斷，務必把完整答案說完再加收尾反問。

【代檢須知】無需預約，現場依序辦理；攜帶行照 + 強制險有效期限 30 日以上

【原則】不編造建檔外資訊；意圖不明確時先確認一次，仍不明確 → 呼叫 transfer_to_human

---

【範例 2 — 電梯維修服務中心（結構化資料收集 + 工具呼叫型）】
你是電梯維修公司的電話語音客服 AI Agent，使用繁體中文，語氣冷靜務實（不用過度熱情，來電者很可能正在受困或焦慮）。

【你的核心任務】
你的任務不是決定怎麼修，而是：
1. 蒐集完整報修資訊
2. 判斷事故情境與緊急程度
3. 複誦確認後正確建立工單
4. 必要時立即轉真人處理

你不得：
- 提供維修建議
- 推測故障原因
- 與使用者閒聊
- 自行降低案件緊急程度

【對話流程】
接聽 → 蒐集資料（Slot Filling）→ 內部分類 → 複誦確認 → 建立工單 → 依案件類型回覆 → 結束

【必須收集的資訊】
- building_name：大樓名稱或棟別
- elevator_id：電梯編號
- contact_phone：聯絡電話
- description：故障狀況（用來電者原話，不要重組或潤飾）

【緊急程度判斷】
以下必須設為 EMERGENCY，不可降級：
- 人被關在電梯、受傷、跌倒、老人或小孩受困
- 冒煙、燒焦味、火花

【複誦確認話術】
「我幫您確認一下，[棟別] 的 [電梯編號]，目前狀況是『[description]』，聯絡電話是 [電話]，請問這樣正確嗎？」

只有使用者明確確認後才能建立工單。

【原則】不編造建檔外資訊；若使用者詢問價格、保固、帳務問題，直接 transfer_to_human。`;

const ENHANCE_SYSTEM = `你是一位專業的語音 AI Agent 系統提示詞工程師。
使用者會提供一份現有的 system prompt，以及他們希望改進的方向。
你的任務是在保留原有架構和風格的基礎上，針對使用者指定的方向進行改進。

規則：
- 保留原 prompt 中已經良好的部分，只改動有問題或需要加強的地方
- 改進後的 prompt 應與原版風格一致
- 不要完全重寫——這是協作補強，不是取代
- 用繁體中文撰寫（除非原 prompt 使用其他語言）
- 只輸出改進後的完整 system prompt 本體，不要加任何說明或比較`;

async function callLM(systemPrompt: string, userMessage: string): Promise<string> {
  const res = await fetch(`${LM_STUDIO_URL}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: 'Bearer lm-studio',
    },
    body: JSON.stringify({
      model: LM_MODEL,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userMessage },
      ],
      temperature: 0.7,
      max_tokens: 4096,
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    console.error('[generate-prompt] LM Studio error:', res.status, body);
    throw new Error(`LM Studio error: ${res.status}`);
  }

  const data = await res.json();
  const text = data?.choices?.[0]?.message?.content;
  if (!text) throw new Error('No content generated');
  return text as string;
}

export async function POST(req: Request) {
  let body: {
    mode?: 'create' | 'enhance';
    description?: string;
    existing_prompt?: string;
    direction?: string;
  };

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON body' }, { status: 400 });
  }

  const mode = body.mode ?? 'create';

  try {
    if (mode === 'enhance') {
      const existing = body.existing_prompt?.trim();
      const direction = body.direction?.trim();
      if (!existing) {
        return NextResponse.json(
          { detail: 'existing_prompt is required for enhance mode' },
          { status: 400 }
        );
      }
      if (!direction) {
        return NextResponse.json(
          { detail: 'direction is required for enhance mode' },
          { status: 400 }
        );
      }
      if (existing.length > 8000 || direction.length > 2000) {
        return NextResponse.json({ detail: 'Input too long' }, { status: 400 });
      }

      const userMessage = `【現有 System Prompt】\n${existing}\n\n【希望改進的方向】\n${direction}`;
      const prompt = await callLM(ENHANCE_SYSTEM, userMessage);
      return NextResponse.json({ prompt });
    }

    // default: create
    const description = body.description?.trim();
    if (!description) {
      return NextResponse.json({ detail: 'description is required' }, { status: 400 });
    }
    if (description.length > 2000) {
      return NextResponse.json(
        { detail: 'description too long (max 2000 chars)' },
        { status: 400 }
      );
    }

    const prompt = await callLM(CREATE_SYSTEM, description);
    return NextResponse.json({ prompt });
  } catch (e) {
    console.error('[generate-prompt] Error:', e);
    return NextResponse.json({ detail: (e as Error).message }, { status: 502 });
  }
}
