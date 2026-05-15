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
