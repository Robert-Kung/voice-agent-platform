'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronRight, Sparkles } from 'lucide-react';
import { markdown } from '@codemirror/lang-markdown';
import { defaultHighlightStyle, syntaxHighlighting } from '@codemirror/language';
import { EditorState } from '@codemirror/state';
import { EditorView, placeholder as cmPlaceholder, keymap, lineNumbers } from '@codemirror/view';
import { badgeText, fieldLabel } from '@/components/admin/editor-type-scale';
import type { UseProfileFormReturn } from '@/hooks/use-profile-form';

const inputClass =
  'border-border bg-background text-foreground w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40';

interface PromptEditorProps {
  form: UseProfileFormReturn;
  onGenerateClick?: () => void;
  onSave?: () => void;
}

/**
 * Center area of the profile editor v2.
 * Shows: Welcome Message + Welcome Instructions + System Prompt (CodeMirror).
 */
export function PromptEditor({ form, onGenerateClick, onSave }: PromptEditorProps) {
  const { known, updateKnown } = form;

  const charCount = known.instructions?.length ?? 0;
  const tokenEstimate = Math.ceil(charCount / 4);

  // Active welcome field follows the engine (D5): pipeline reads Welcome Message
  // verbatim; realtime generates from Welcome Instructions. The inactive field is
  // collapsed (de-emphasized) but never cleared — it round-trips and is ready when
  // the engine mode changes.
  const messageActive = form.modelsMode === 'pipeline';

  const welcomeMessage = (
    <WelcomeField
      label="Welcome Message"
      hint="pipeline TTS 逐字朗讀"
      active={messageActive}
      inactiveNote="pipeline 模式才生效"
      value={known.welcome_message ?? ''}
      onChange={(v) => updateKnown('welcome_message', v)}
      placeholder="進線第一句歡迎語…"
    />
  );

  const welcomeInstructions = (
    <WelcomeField
      label="Welcome Instructions"
      hint="realtime 模式 — Gemini 自由生成開場"
      active={!messageActive}
      inactiveNote="realtime 模式才生效"
      value={known.welcome_instructions ?? ''}
      onChange={(v) => updateKnown('welcome_instructions', v)}
      placeholder="向來電者打招呼，簡短介紹自己並詢問需要什麼協助。"
    />
  );

  return (
    <div className="flex h-full flex-col space-y-5">
      {/* Welcome helper — only one mode applies */}
      <p className="text-foreground/50 text-xs leading-relaxed">
        <span className="font-medium">僅一種模式生效</span>
        ：pipeline 模式逐字朗讀 Welcome Message；realtime 模式由 Gemini 依 Welcome Instructions
        生成。依目前引擎，未生效的欄位收起（值保留）。
      </p>

      {/* Active field first, inactive collapsed below it. */}
      {messageActive ? (
        <>
          {welcomeMessage}
          {welcomeInstructions}
        </>
      ) : (
        <>
          {welcomeInstructions}
          {welcomeMessage}
        </>
      )}

      {/* System Prompt — dominant, takes remaining space */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="mb-1 flex items-center justify-between">
          <label className={`text-foreground/70 ${fieldLabel}`}>
            System Prompt
            <span className="text-foreground/40 ml-2 font-normal">(instructions)</span>
          </label>
          {onGenerateClick && (
            <button
              type="button"
              onClick={onGenerateClick}
              className="border-border text-foreground/60 hover:bg-foreground/5 hover:text-foreground flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs transition-colors"
            >
              <Sparkles size={14} />
              Generate
            </button>
          )}
        </div>
        <SystemPromptEditor
          value={known.instructions ?? ''}
          onChange={(val) => updateKnown('instructions', val)}
          onSave={onSave}
        />
        <div className="text-foreground/40 mt-1 text-right font-mono text-[11px]">
          {charCount} chars · ~{tokenEstimate} tokens
        </div>
      </div>
    </div>
  );
}

// ── Welcome field (active emphasized / inactive collapsed, D5) ──────

interface WelcomeFieldProps {
  label: string;
  hint: string;
  active: boolean;
  inactiveNote: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}

function WelcomeField({
  label,
  hint,
  active,
  inactiveNote,
  value,
  onChange,
  placeholder,
}: WelcomeFieldProps) {
  const [expanded, setExpanded] = useState(false);

  if (!active && !expanded) {
    // De-emphasized: a collapsed row, never cleared. Expandable to edit ahead of
    // an engine switch; a "has content" dot hints there's a preserved value.
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="border-border/70 text-foreground/50 hover:bg-foreground/5 hover:text-foreground flex w-full items-center gap-2 rounded-md border border-dashed px-3 py-1.5 text-left"
      >
        <ChevronRight size={13} className="shrink-0" />
        <span className={fieldLabel}>{label}</span>
        <span className={`text-foreground/40 ${badgeText}`}>{inactiveNote}</span>
        {value.trim() && <span className="text-foreground/30 ml-auto text-[10px]">已填內容</span>}
      </button>
    );
  }

  return (
    <div>
      <label className={`text-foreground/70 mb-1 block ${fieldLabel}`}>
        {label}
        <span className="text-foreground/40 ml-2 font-normal">({hint})</span>
        {active ? (
          <span className="ml-2 rounded bg-green-500/15 px-1.5 py-0.5 text-[10px] font-medium text-green-700 dark:text-green-400">
            生效中
          </span>
        ) : (
          <span className="text-foreground/40 ml-2 rounded border border-dashed px-1.5 py-0.5 text-[10px] font-normal">
            {inactiveNote}
          </span>
        )}
      </label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={2}
        placeholder={placeholder}
        className={`${inputClass} resize-y`}
      />
    </div>
  );
}

// ── CodeMirror-based System Prompt Editor ──────────────────────────

interface SystemPromptEditorProps {
  value: string;
  onChange: (val: string) => void;
  onSave?: () => void;
}

function SystemPromptEditor({ value, onChange, onSave }: SystemPromptEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);

  // Keep refs fresh
  onChangeRef.current = onChange;
  onSaveRef.current = onSave;

  // Stable initial value snapshot so createEditor isn't reinvoked on each keystroke
  const initialValueRef = useRef(value);
  // Track latest value via ref (used by createEditor without retriggering it)
  const latestValueRef = useRef(value);
  latestValueRef.current = value;

  const createEditor = useCallback(() => {
    if (!containerRef.current) return;

    // Clean up existing
    if (viewRef.current) {
      viewRef.current.destroy();
      viewRef.current = null;
    }

    const updateListener = EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        onChangeRef.current(update.state.doc.toString());
      }
    });

    const saveKeymap = keymap.of([
      {
        key: 'Mod-Enter',
        run: () => {
          onSaveRef.current?.();
          return true;
        },
      },
    ]);

    const theme = EditorView.theme({
      '&': {
        height: '100%',
        fontSize: '12px',
        border: '1px solid var(--border)',
        borderRadius: '0.375rem',
        backgroundColor: 'transparent',
      },
      '&.cm-focused': {
        outline: 'none',
        boxShadow: '0 0 0 2px hsl(var(--primary) / 0.4)',
      },
      '.cm-scroller': {
        fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
        lineHeight: '1.6',
      },
      '.cm-content': {
        padding: '12px 0',
        color: 'hsl(var(--foreground))',
        caretColor: 'hsl(var(--foreground))',
      },
      '.cm-gutters': {
        backgroundColor: 'hsl(var(--foreground) / 0.03)',
        borderRight: '1px solid var(--border)',
        color: 'hsl(var(--foreground) / 0.4)',
      },
      '.cm-lineNumbers .cm-gutterElement': {
        padding: '0 8px 0 12px',
        minWidth: '3em',
        color: 'hsl(var(--foreground) / 0.3)',
        fontSize: '12px',
      },
      '.cm-activeLine': {
        backgroundColor: 'hsl(var(--foreground) / 0.03)',
      },
      '.cm-activeLineGutter': {
        backgroundColor: 'hsl(var(--foreground) / 0.05)',
      },
      '.cm-selectionBackground, &.cm-focused .cm-selectionBackground, ::selection': {
        backgroundColor: 'hsl(var(--primary) / 0.2)',
      },
    });

    const state = EditorState.create({
      doc: initialValueRef.current,
      extensions: [
        lineNumbers(),
        markdown(),
        syntaxHighlighting(defaultHighlightStyle),
        theme,
        updateListener,
        saveKeymap,
        cmPlaceholder('主 Agent 的 system prompt…'),
        EditorView.lineWrapping,
      ],
    });

    viewRef.current = new EditorView({
      state,
      parent: containerRef.current,
    });
  }, []);

  // Initialize editor once
  useEffect(() => {
    createEditor();
    return () => {
      viewRef.current?.destroy();
      viewRef.current = null;
    };
  }, [createEditor]);

  // Sync external value changes (e.g., from AI Generate)
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const currentDoc = view.state.doc.toString();
    if (currentDoc !== value) {
      view.dispatch({
        changes: { from: 0, to: currentDoc.length, insert: value },
      });
    }
  }, [value]);

  return <div ref={containerRef} className="min-h-[400px] flex-1 overflow-hidden rounded-md" />;
}
