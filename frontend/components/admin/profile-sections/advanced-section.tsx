'use client';

import type { UseProfileFormReturn } from '@/hooks/use-profile-form';
import { CollapsibleSection } from '../collapsible-section';

interface AdvancedSectionProps {
  form: UseProfileFormReturn;
}

export function AdvancedSection({ form }: AdvancedSectionProps) {
  const { extraJson, setExtraJson } = form;
  const hasExtra = extraJson.trim() !== '' && extraJson.trim() !== '{}';

  return (
    <CollapsibleSection
      title="Advanced"
      id="section-advanced"
      badge={hasExtra ? '●' : undefined}
      defaultOpen={false}
    >
      <div className="space-y-2">
        <p className="text-foreground/50 text-[10px]">
          額外欄位（如 schedule / closed_days）。儲存時與表單合併。
        </p>
        <textarea
          value={extraJson}
          onChange={(e) => setExtraJson(e.target.value)}
          rows={12}
          spellCheck={false}
          className="border-border bg-background text-foreground focus:ring-primary/40 w-full resize-y rounded-md border px-3 py-2 font-mono text-xs focus:ring-2 focus:outline-none"
        />
      </div>
    </CollapsibleSection>
  );
}
