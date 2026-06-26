'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Settings2, SlidersHorizontal } from 'lucide-react';
import { DirtyBadge } from '@/components/admin/dirty-badge';

interface ProfileEditorHeaderProps {
  displayName: string;
  profileName: string;
  language?: string;
  isDirty: boolean;
  isNew: boolean;
  saving: boolean;
  trying: boolean;
  onSave: () => void;
  onTry: () => void;
  onSaveAndTry?: () => void;
  onPanelToggle?: () => void;
  modeControl?: React.ReactNode;
  /** Short profile-declared stack summary (e.g. "Realtime · Gemini Live"). */
  stackSummary?: string;
  /** Open the model/voice stack settings panel (D7 — chip is the entry point). */
  onStackClick?: () => void;
}

/**
 * Sticky header for the profile editor v2.
 * Shows: ← Back | Profile name | Stack chips | Save / Try
 */
export function ProfileEditorHeader({
  displayName,
  profileName,
  language,
  isDirty,
  isNew,
  saving,
  trying,
  onSave,
  onTry,
  onSaveAndTry,
  onPanelToggle,
  modeControl,
  stackSummary,
  onStackClick,
}: ProfileEditorHeaderProps) {
  const [showConfirm, setShowConfirm] = useState(false);

  return (
    <div className="flex items-center gap-4 px-6 py-3">
      {/* Left: back + identity */}
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <Link
          href="/admin/profiles"
          aria-label="返回 Profiles 列表"
          className="text-foreground/50 hover:text-foreground hover:bg-foreground/5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md"
        >
          <ArrowLeft size={18} />
        </Link>
        <div className="min-w-0">
          <h1 className="text-foreground truncate text-lg font-semibold">
            {isNew ? 'New Profile' : displayName || profileName}
          </h1>
          {!isNew && <p className="text-foreground/40 truncate font-mono text-xs">{profileName}</p>}
        </div>
        {isDirty && <DirtyBadge title="未儲存的變更" />}
      </div>

      {/* Center: the two orthogonal-but-coupled mode axes, each in a labeled
          group so a first-time viewer can tell them apart at rest (spec: header
          strategy/engine axes visually grouped). 策略 (editor_mode) → 引擎
          (models.mode, via the Stack chip); the → hints the coupling (graph
          needs pipeline). Hidden < md, where the controls collapse as before. */}
      <div className="hidden items-center gap-2 md:flex">
        {modeControl && (
          <div className="border-border/70 flex items-center gap-2 rounded-lg border border-dashed px-2 py-1">
            <span className="text-foreground/40 text-[10px] font-medium tracking-wider uppercase">
              策略
            </span>
            {modeControl}
          </div>
        )}
        <span className="text-foreground/30 shrink-0 text-xs" aria-hidden>
          →
        </span>
        <div className="border-border/70 flex items-center gap-2 rounded-lg border border-dashed px-2 py-1">
          <span className="text-foreground/40 text-[10px] font-medium tracking-wider uppercase">
            引擎
          </span>
          {/* Stack chip — an explicit editable entry point (accent fill + cog +
              hover ring), distinct from the passive language status pill (spec:
              Stack chip reads as editable, not a status badge). */}
          <button
            type="button"
            onClick={onStackClick}
            title="開啟模型 / 語音設定"
            className="bg-primary/10 text-primary ring-primary/20 hover:bg-primary/15 hover:ring-primary/40 inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium whitespace-nowrap ring-1 transition-colors"
          >
            <Settings2 size={12} />
            {stackSummary || 'Stack'}
          </button>
          {language && (
            <span className="bg-foreground/5 border-border text-foreground/60 rounded-full border px-2.5 py-0.5 text-[11px] whitespace-nowrap">
              {language}
            </span>
          )}
        </div>
      </div>

      {/* Right: actions */}
      <div className="flex shrink-0 items-center gap-2">
        {onPanelToggle && (
          <button
            type="button"
            onClick={onPanelToggle}
            aria-label="Toggle settings panel"
            className="text-foreground/50 hover:text-foreground hover:bg-foreground/5 inline-flex h-8 w-8 items-center justify-center rounded-md md:hidden"
          >
            <SlidersHorizontal size={16} />
          </button>
        )}
        <button
          type="button"
          onClick={onSave}
          disabled={saving || (!isDirty && !isNew)}
          className="bg-primary text-primary-foreground rounded-md px-4 py-1.5 text-sm font-medium transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {saving ? (
            'Saving…'
          ) : (
            <>
              {isNew ? 'Create' : 'Save'}
              <kbd className="border-primary-foreground/30 text-primary-foreground/70 ml-1.5 hidden rounded border px-1 font-mono text-[10px] sm:inline-block">
                ⌘⏎
              </kbd>
            </>
          )}
        </button>
        {!isNew && (
          <div className="relative">
            <button
              type="button"
              onClick={() => {
                if (isDirty) {
                  setShowConfirm(true);
                } else {
                  onTry();
                }
              }}
              disabled={trying}
              title="啟動本機 connect-mode agent 測試"
              className="border-border hover:bg-foreground/5 rounded-md border px-4 py-1.5 text-sm disabled:opacity-50"
            >
              {trying ? '啟動中…' : 'Try ▶'}
            </button>
            {showConfirm && (
              <div className="border-border bg-background absolute top-full right-0 z-10 mt-1 flex items-center gap-2 rounded-md border px-3 py-2 text-xs whitespace-nowrap shadow-sm">
                <span>未儲存，要先儲存後再 Try 嗎？</span>
                <button
                  type="button"
                  onClick={() => {
                    onSaveAndTry?.();
                    setShowConfirm(false);
                  }}
                  className="text-primary font-medium"
                >
                  儲存並 Try
                </button>
                <button
                  type="button"
                  onClick={() => setShowConfirm(false)}
                  className="text-foreground/50"
                >
                  取消
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
