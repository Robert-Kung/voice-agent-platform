'use client';

import { useCallback, useEffect, useRef } from 'react';
import { markdown } from '@codemirror/lang-markdown';
import { EditorState } from '@codemirror/state';
import { oneDark } from '@codemirror/theme-one-dark';
import { EditorView, placeholder as cmPlaceholder, keymap, lineNumbers } from '@codemirror/view';
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

  return (
    <div className="flex h-full flex-col space-y-5">
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
          <span className="text-foreground/40 ml-2 font-normal">
            (realtime 模式 — Gemini 自由生成開場)
          </span>
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
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="mb-1 flex items-center justify-between">
          <label className="text-foreground/60 text-xs font-medium">
            System Prompt
            <span className="text-foreground/40 ml-2 font-normal">(instructions)</span>
          </label>
          {onGenerateClick && (
            <button
              type="button"
              onClick={onGenerateClick}
              className="border-border text-foreground/60 hover:bg-foreground/5 hover:text-foreground flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs transition-colors"
            >
              ✨ Generate
            </button>
          )}
        </div>
        <SystemPromptEditor
          value={known.instructions ?? ''}
          onChange={(val) => updateKnown('instructions', val)}
          onSave={onSave}
        />
      </div>
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
      },
      '.cm-gutters': {
        backgroundColor: 'transparent',
        borderRight: '1px solid var(--border)',
      },
      '.cm-lineNumbers .cm-gutterElement': {
        padding: '0 8px 0 12px',
        minWidth: '3em',
        color: 'hsl(var(--foreground) / 0.3)',
        fontSize: '11px',
      },
    });

    const state = EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        markdown(),
        oneDark,
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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Initialize editor
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
