import { NextResponse } from 'next/server';

const GOOGLE_API_KEY = process.env.GOOGLE_API_KEY;
const MODEL = 'gemini-2.0-flash-lite';

const SYSTEM_INSTRUCTION = `你是一位專業的語音 AI Agent 系統提示詞工程師。
使用者會描述一個業務場景（行業類型、功能需求、語氣風格），你要產生一份完整的 system prompt。

產出格式要求：
- 用繁體中文撰寫（除非使用者指定其他語言）
- 包含角色定義、核心任務、對話流程、重要規則
- 語氣自然、適合語音對話（避免過度書面化）
- 使用 markdown 格式（## 標題分節）
- 加入【重要規則】區塊提醒：一次問一個問題、說話簡潔、不要重複已知資訊

只輸出 system prompt 本體，不要加任何前綴說明或後綴評論。`;

export async function POST(req: Request) {
  if (!GOOGLE_API_KEY) {
    return NextResponse.json(
      { detail: 'GOOGLE_API_KEY not configured on server' },
      { status: 500 }
    );
  }

  let body: { description?: string };
  try {
    body = (await req.json()) as { description?: string };
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON body' }, { status: 400 });
  }

  const description = body.description?.trim();
  if (!description) {
    return NextResponse.json({ detail: 'description is required' }, { status: 400 });
  }

  // Limit input length to prevent abuse
  if (description.length > 2000) {
    return NextResponse.json({ detail: 'description too long (max 2000 chars)' }, { status: 400 });
  }

  try {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${GOOGLE_API_KEY}`;

    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        system_instruction: {
          parts: [{ text: SYSTEM_INSTRUCTION }],
        },
        contents: [
          {
            role: 'user',
            parts: [{ text: description }],
          },
        ],
        generationConfig: {
          temperature: 0.7,
          maxOutputTokens: 4096,
        },
      }),
    });

    if (!response.ok) {
      const errorBody = await response.text();
      console.error('[generate-prompt] Gemini API error:', response.status, errorBody);
      return NextResponse.json({ detail: `Gemini API error: ${response.status}` }, { status: 502 });
    }

    const data = await response.json();
    const text = data?.candidates?.[0]?.content?.parts?.[0]?.text;

    if (!text) {
      return NextResponse.json({ detail: 'No content generated' }, { status: 502 });
    }

    return NextResponse.json({ prompt: text });
  } catch (e) {
    console.error('[generate-prompt] Error:', e);
    return NextResponse.json(
      { detail: `Internal error: ${(e as Error).message}` },
      { status: 500 }
    );
  }
}
