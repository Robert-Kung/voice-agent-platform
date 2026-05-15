'use client';

import { CollapsibleSection } from '../collapsible-section';
import type { UseProfileFormReturn } from '@/hooks/use-profile-form';

const inputClass =
  'border-border bg-background text-foreground w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40';

interface HoursSectionProps {
  form: UseProfileFormReturn;
}

export function HoursSection({ form }: HoursSectionProps) {
  const { known, addService, renameService, updateService, removeService } = form;
  const services = known.services || {};
  const count = Object.keys(services).length;

  return (
    <CollapsibleSection
      title="Service Hours"
      id="section-hours"
      badge={count > 0 ? `${count}` : undefined}
      defaultOpen={count > 0}
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-foreground/50 text-[10px]">
            營業時間嵌入 instructions，搭配 get_current_time 判斷
          </p>
          <button
            type="button"
            onClick={addService}
            className="border-border hover:bg-foreground/5 rounded border px-2 py-0.5 text-xs shrink-0"
          >
            + Add
          </button>
        </div>

        {count === 0 && (
          <p className="text-foreground/50 text-center text-xs py-3 border border-dashed rounded-md">
            未設定
          </p>
        )}

        <div className="space-y-2">
          {Object.entries(services).map(([key, svc]) => (
            <div key={key} className="border-border bg-foreground/5 space-y-2 rounded-md border p-2">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  defaultValue={key}
                  onBlur={(e) => renameService(key, e.target.value.trim())}
                  className="border-border bg-background rounded border px-2 py-0.5 font-mono text-xs flex-1 min-w-0"
                />
                <label className="flex items-center gap-1 text-xs shrink-0">
                  <input
                    type="checkbox"
                    checked={!!svc.always_open}
                    onChange={(e) => updateService(key, { always_open: e.target.checked })}
                    className="size-3"
                  />
                  24h
                </label>
                <button
                  type="button"
                  onClick={() => removeService(key)}
                  className="text-red-500 text-xs hover:text-red-400"
                >
                  ✕
                </button>
              </div>
              {!svc.always_open && (
                <input
                  type="text"
                  value={typeof svc.hours_text === 'string' ? svc.hours_text : ''}
                  onChange={(e) => updateService(key, { hours_text: e.target.value })}
                  placeholder="平日 8:00-18:00，週六 8:00-12:00，週日休息"
                  disabled={typeof svc.hours_text === 'object'}
                  className={`${inputClass} text-xs`}
                />
              )}
            </div>
          ))}
        </div>
      </div>
    </CollapsibleSection>
  );
}
