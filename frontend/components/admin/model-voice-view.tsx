'use client';

import { useEffect } from 'react';
import { ArrowLeft, Layers } from 'lucide-react';
import { sectionTitle } from '@/components/admin/editor-type-scale';
import { StackSettings } from '@/components/admin/stack-settings';
import type { UseProfileFormReturn } from '@/hooks/use-profile-form';

interface ModelVoiceViewProps {
  form: UseProfileFormReturn;
  onBack: () => void;
  /**
   * ESC returns to the editor only while no modal/overlay sits on top (D1 ESC
   * priority). The page passes false when a page-level modal is open so this
   * view does not steal/​double-fire their Escape.
   */
  escEnabled: boolean;
}

/**
 * Full-width Model & Voice view (D1/D2). Replaces the cramped center modal: the
 * header Stack chip view-swaps to this in-place, so the editor form stays
 * mounted and the unsaved draft is preserved. The two-column wrapper gives the
 * stack controls room to breathe; the control logic itself lives unchanged in
 * StackSettings (engine tabs, provider/model/voice/language reads & resets).
 */
export function ModelVoiceView({ form, onBack, escEnabled }: ModelVoiceViewProps) {
  useEffect(() => {
    if (!escEnabled) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onBack();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [escEnabled, onBack]);

  return (
    <div className="mx-auto w-full max-w-5xl p-6">
      <button
        type="button"
        onClick={onBack}
        className="text-foreground/60 hover:text-foreground hover:bg-foreground/5 mb-4 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm"
      >
        <ArrowLeft size={15} />
        返回編輯
        <kbd className="border-border text-foreground/40 ml-1 hidden rounded border px-1 font-mono text-[10px] sm:inline-block">
          esc
        </kbd>
      </button>

      <div className="grid gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        {/* Left: context column — what this view configures (global base layer). */}
        <div className="md:sticky md:top-0 md:self-start">
          <h1 className={`text-foreground flex items-center gap-2 ${sectionTitle}`}>
            <Layers size={16} />
            模型與語音
          </h1>
          <p className="text-foreground/60 mt-2 text-sm leading-relaxed">
            這層設定套用於整個 agent（global 底層），在 prompt 與 graph
            模式下都生效。先選執行引擎，再為各元件挑 provider / 模型 / 語音 /
            語言。未宣告的欄位走編譯預設。
          </p>
        </div>

        {/* Right: the stack controls — engine cards + TTS / LLM / STT segments. */}
        <div>
          <StackSettings form={form} />
        </div>
      </div>
    </div>
  );
}
