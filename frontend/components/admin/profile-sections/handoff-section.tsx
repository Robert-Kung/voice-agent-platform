'use client';

import type { UseProfileFormReturn } from '@/hooks/use-profile-form';
import { CollapsibleSection } from '../collapsible-section';

const inputClass =
  'border-border bg-background text-foreground w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40';

interface HandoffSectionProps {
  form: UseProfileFormReturn;
}

export function HandoffSection({ form }: HandoffSectionProps) {
  const { known, updateHandoff } = form;
  const enabled = !!known.human_operator?.enabled;

  return (
    <CollapsibleSection
      title="Human Handoff"
      id="section-handoff"
      badge={enabled ? '● On' : 'Off'}
      defaultOpen={enabled}
    >
      <div className="space-y-3">
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => updateHandoff('enabled', e.target.checked)}
          />
          啟用真人轉接
        </label>
        <p className="text-foreground/50 text-[10px]">開啟後自動掛上 transfer_to_human 工具</p>

        {enabled && (
          <div className="space-y-2">
            <div>
              <label className="text-foreground/60 text-[10px]">Greeting (轉接後第一句)</label>
              <input
                type="text"
                value={known.human_operator?.greeting ?? ''}
                onChange={(e) => updateHandoff('greeting', e.target.value)}
                placeholder="告知已轉接門市人員…"
                className={`${inputClass} text-xs`}
              />
            </div>
            <div>
              <label className="text-foreground/60 text-[10px]">
                Tool Description (何時觸發轉接)
              </label>
              <textarea
                value={known.human_operator?.tool_description ?? ''}
                onChange={(e) => updateHandoff('tool_description', e.target.value)}
                rows={2}
                placeholder="留空用通用預設。可寫具體觸發情境，例如：緊急派工後、建單失敗、或詢問價格/合約時呼叫"
                className={`${inputClass} resize-y text-xs`}
              />
              <p className="text-foreground/40 mt-0.5 text-[10px]">
                此描述會送進模型，決定它何時呼叫 transfer_to_human
              </p>
            </div>
            <div>
              <label className="text-foreground/60 text-[10px]">Instructions (人工 persona)</label>
              <textarea
                value={known.human_operator?.instructions ?? ''}
                onChange={(e) => updateHandoff('instructions', e.target.value)}
                rows={2}
                placeholder="你是 XX 的門市人員…"
                className={`${inputClass} resize-y text-xs`}
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-foreground/60 text-[10px]">Voice</label>
                <input
                  type="text"
                  value={known.human_operator?.voice ?? ''}
                  onChange={(e) => updateHandoff('voice', e.target.value)}
                  placeholder="Puck"
                  className={`${inputClass} text-xs`}
                />
              </div>
              <div>
                <label className="text-foreground/60 text-[10px]">Transfer Message</label>
                <input
                  type="text"
                  value={known.human_operator?.transfer_message ?? ''}
                  onChange={(e) => updateHandoff('transfer_message', e.target.value)}
                  placeholder="正在為您轉接…"
                  className={`${inputClass} text-xs`}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
