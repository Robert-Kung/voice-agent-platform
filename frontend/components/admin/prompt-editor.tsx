'use client';

import type { UseProfileFormReturn } from '@/hooks/use-profile-form';

const inputClass =
  'border-border bg-background text-foreground w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40';

interface PromptEditorProps {
  form: UseProfileFormReturn;
  onGenerateClick?: () => void;
}

/**
 * Center area of the profile editor v2.
 * Shows: Welcome Message + Welcome Instructions + System Prompt (dominant).
 */
export function PromptEditor({ form, onGenerateClick }: PromptEditorProps) {
  const { known, updateKnown } = form;

  return (
    <div className="space-y-5 h-full flex flex-col">
      {/* Welcome Message — compact */}
      <div>
        <label className="text-foreground/60 mb-1 block text-xs font-medium">
          Welcome Message
          <span className="text-foreground/40 ml-2 font-normal">(pipeline TTS 逐字朗讀)</span>
        </label>
        <textarea
          value={known.welcome_message ?? ''}
          onChange={(e) => updateKnown('welcome_message', e.target.value)}
          rows={2}
          placeholder="進線第一句歡迎語…"
          className={`${inputClass} resize-y`}
        />
      </div>

      {/* Welcome Instructions — for realtime mode */}
      <div>
        <label className="text-foreground/60 mb-1 block text-xs font-medium">
          Welcome Instructions
          <span className="text-foreground/40 ml-2 font-normal">(realtime 模式 — Gemini 自由生成開場)</span>
        </label>
        <textarea
          value={known.welcome_instructions ?? ''}
          onChange={(e) => updateKnown('welcome_instructions', e.target.value)}
          rows={2}
          placeholder="向來電者打招呼，簡短介紹自己並詢問需要什麼協助。"
          className={`${inputClass} resize-y`}
        />
      </div>

      {/* System Prompt — dominant, takes remaining space */}
      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-1">
          <label className="text-foreground/60 text-xs font-medium">
            System Prompt
            <span className="text-foreground/40 ml-2 font-normal">(instructions)</span>
          </label>
          {onGenerateClick && (
            <button
              type="button"
              onClick={onGenerateClick}
              className="flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-xs text-foreground/60 hover:bg-foreground/5 hover:text-foreground transition-colors"
            >
              ✨ Generate
            </button>
          )}
        </div>
        <textarea
          value={known.instructions ?? ''}
          onChange={(e) => updateKnown('instructions', e.target.value)}
          placeholder="主 Agent 的 system prompt…"
          className={`${inputClass} flex-1 min-h-[400px] resize-y font-mono text-xs leading-relaxed`}
        />
      </div>
    </div>
  );
}
