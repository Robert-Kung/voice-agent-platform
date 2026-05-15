'use client';

import { useState } from 'react';
import { CollapsibleSection } from '../collapsible-section';
import type { UseProfileFormReturn } from '@/hooks/use-profile-form';
import type { QaMode } from '@/hooks/use-profile-form';

const inputClass =
  'border-border bg-background text-foreground w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40';

interface QaSectionProps {
  form: UseProfileFormReturn;
}

export function QaSection({ form }: QaSectionProps) {
  const { known, qaList, setQaMode, addQaEntry, updateQaEntry, removeQaEntry } = form;
  const qaCount = qaList.length;
  const mode = known.qa_mode ?? 'inline';

  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const query = search.trim().toLowerCase();
  const filtered = qaList
    .map((qa, idx) => ({ qa, idx }))
    .filter(({ qa }) => {
      if (!query) return true;
      const inKw = (qa.keywords || []).some((k) => k.toLowerCase().includes(query));
      const inAns = (qa.answer || '').toLowerCase().includes(query);
      return inKw || inAns;
    });

  const badgeText = `${qaCount} · ${mode}`;

  return (
    <CollapsibleSection
      title="Knowledge Base / QA"
      id="section-qa"
      badge={badgeText}
      defaultOpen={qaCount > 0}
    >
      <div className="space-y-3">
        {/* Mode toggle */}
        <div className="flex items-center justify-between">
          <div className="border-border inline-flex overflow-hidden rounded border text-xs">
            {(['inline', 'tool'] as QaMode[]).map((m) => {
              const active = mode === m;
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => setQaMode(m)}
                  className={`px-2 py-1 ${active ? 'bg-foreground/10 font-medium' : 'hover:bg-foreground/5'}`}
                >
                  {m === 'inline' ? 'Inline' : 'Tool call'}
                </button>
              );
            })}
          </div>
          <button
            type="button"
            onClick={addQaEntry}
            className="border-border hover:bg-foreground/5 rounded border px-2 py-0.5 text-xs"
          >
            + Add
          </button>
        </div>

        {/* Search */}
        {qaCount > 0 && (
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="🔍 搜尋 keywords / answer…"
            className={`${inputClass} text-xs`}
          />
        )}

        {/* QA list */}
        {qaCount === 0 && (
          <p className="text-foreground/50 text-center text-xs py-3 border border-dashed rounded-md">
            尚無 QA
          </p>
        )}
        <div className="space-y-1.5 max-h-[400px] overflow-y-auto">
          {filtered.map(({ qa, idx }) => {
            const isOpen = expanded.has(idx);
            const kwPreview = (qa.keywords || []).join('、');
            return (
              <div key={idx} className="border-border bg-foreground/5 rounded-md border">
                <div className="flex items-stretch">
                  <button
                    type="button"
                    onClick={() => {
                      setExpanded((s) => {
                        const next = new Set(s);
                        if (next.has(idx)) next.delete(idx);
                        else next.add(idx);
                        return next;
                      });
                    }}
                    className="hover:bg-foreground/5 flex flex-1 items-center gap-2 px-2 py-1.5 text-left min-w-0"
                  >
                    <span className="text-foreground/50 w-3 text-[10px]">{isOpen ? '▾' : '▸'}</span>
                    <span className="truncate text-xs">{kwPreview || '(no keywords)'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => removeQaEntry(idx)}
                    className="border-border hover:bg-foreground/10 border-l px-2 text-xs text-red-500"
                  >
                    ✕
                  </button>
                </div>
                {isOpen && (
                  <div className="border-border space-y-2 border-t p-2">
                    <div>
                      <label className="text-foreground/60 text-[10px]">Keywords（逗號分隔）</label>
                      <input
                        type="text"
                        value={(qa.keywords || []).join('、')}
                        onChange={(e) =>
                          updateQaEntry(idx, {
                            keywords: e.target.value
                              .split(/[,，、]/)
                              .map((k) => k.trim())
                              .filter(Boolean),
                          })
                        }
                        className={`${inputClass} text-xs`}
                      />
                    </div>
                    <div>
                      <label className="text-foreground/60 text-[10px]">Answer</label>
                      <textarea
                        value={qa.answer ?? ''}
                        onChange={(e) => updateQaEntry(idx, { answer: e.target.value })}
                        rows={2}
                        className={`${inputClass} text-xs resize-y`}
                      />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </CollapsibleSection>
  );
}
