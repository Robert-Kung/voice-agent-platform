'use client';

import type { UseProfileFormReturn } from '@/hooks/use-profile-form';
import { LANGUAGES, NAME_PATTERN, TIMEZONES } from '@/hooks/use-profile-form';
import { CollapsibleSection } from '../collapsible-section';
import { fieldLabel } from '../editor-type-scale';

const inputClass =
  'border-border bg-background text-foreground w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40';

interface IdentitySectionProps {
  form: UseProfileFormReturn;
}

export function IdentitySection({ form }: IdentitySectionProps) {
  const { name, setName, displayName, setDisplayName, known, updateKnown, isNew } = form;

  return (
    <CollapsibleSection
      title="Identity"
      id="section-identity"
      badge={known.language || undefined}
      defaultOpen={isNew}
    >
      <div className="space-y-3">
        <div>
          <label className={`text-foreground/60 ${fieldLabel}`}>
            Name <span className="text-foreground/40">(unique, immutable)</span>
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={!isNew}
            placeholder="e.g. dental_clinic"
            className={`${inputClass} font-mono text-xs ${!isNew ? 'opacity-60' : ''}`}
          />
          {isNew && (
            <p className="text-foreground/40 mt-0.5 text-[10px]">小寫字母開頭，僅含 a-z 0-9 _</p>
          )}
        </div>
        <div>
          <label className={`text-foreground/60 ${fieldLabel}`}>Display Name</label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="例如：幸福牙醫診所"
            className={`${inputClass} text-xs`}
          />
        </div>
        <div>
          <label className={`text-foreground/60 ${fieldLabel}`}>Agent Name (LiveKit worker)</label>
          <input
            type="text"
            value={known.agent_name ?? ''}
            onChange={(e) => updateKnown('agent_name', e.target.value)}
            placeholder="voice-assistant-clinic"
            className={`${inputClass} font-mono text-xs`}
          />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className={`text-foreground/60 ${fieldLabel}`}>Language</label>
            <select
              value={known.language ?? ''}
              onChange={(e) => updateKnown('language', e.target.value)}
              className={`${inputClass} text-xs`}
            >
              <option value="">—</option>
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={`text-foreground/60 ${fieldLabel}`}>Timezone</label>
            <select
              value={known.timezone ?? ''}
              onChange={(e) => updateKnown('timezone', e.target.value)}
              className={`${inputClass} text-xs`}
            >
              <option value="">—</option>
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </CollapsibleSection>
  );
}
