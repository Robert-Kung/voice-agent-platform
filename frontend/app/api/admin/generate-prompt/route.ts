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
- 使用 markdown 格式（## 標題分節）
- 加入【重要規則】區塊提醒：一次問一個問題、說話簡潔、不要重複已知資訊

只輸出 system prompt 本體，不要加任何前綴說明或後綴評論。`;

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
        return NextResponse.json({ detail: 'existing_prompt is required for enhance mode' }, { status: 400 });
      }
      if (!direction) {
        return NextResponse.json({ detail: 'direction is required for enhance mode' }, { status: 400 });
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
      return NextResponse.json({ detail: 'description too long (max 2000 chars)' }, { status: 400 });
    }

    const prompt = await callLM(CREATE_SYSTEM, description);
    return NextResponse.json({ prompt });
  } catch (e) {
    console.error('[generate-prompt] Error:', e);
    return NextResponse.json({ detail: (e as Error).message }, { status: 502 });
  }
}
