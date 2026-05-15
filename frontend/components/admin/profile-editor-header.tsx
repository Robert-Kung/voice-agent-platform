'use client';

import Link from 'next/link';

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
}: ProfileEditorHeaderProps) {
  return (
    <div className="flex items-center gap-4 px-6 py-3">
      {/* Left: back + identity */}
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <Link
          href="/admin/profiles"
          className="text-foreground/50 hover:text-foreground text-sm shrink-0"
        >
          ←
        </Link>
        <div className="min-w-0">
          <h1 className="text-foreground truncate text-base font-semibold">
            {isNew ? 'New Profile' : displayName || profileName}
          </h1>
          {!isNew && (
            <p className="text-foreground/40 truncate font-mono text-xs">{profileName}</p>
          )}
        </div>
        {isDirty && (
          <span className="shrink-0 text-xs text-amber-500" title="未儲存的變更">●</span>
        )}
      </div>

      {/* Center: Stack chips */}
      <div className="hidden md:flex items-center gap-2">
        <span className="bg-foreground/5 border-border rounded-full border px-2.5 py-0.5 text-[11px] text-foreground/60">
          Realtime
        </span>
        <span className="bg-foreground/5 border-border rounded-full border px-2.5 py-0.5 text-[11px] text-foreground/60">
          Gemini Live
        </span>
        <span className="bg-foreground/5 border-border rounded-full border px-2.5 py-0.5 text-[11px] text-foreground/60">
          Deepgram STT
        </span>
        {language && (
          <span className="bg-foreground/5 border-border rounded-full border px-2.5 py-0.5 text-[11px] text-foreground/60">
            {language}
          </span>
        )}
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-2 shrink-0">
        <button
          type="button"
          onClick={onSave}
          disabled={saving || (!isDirty && !isNew)}
          className="bg-primary text-primary-foreground rounded-md px-4 py-1.5 text-sm font-medium transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {saving ? 'Saving…' : isNew ? 'Create' : 'Save'}
        </button>
        {!isNew && (
          <button
            type="button"
            onClick={onTry}
            disabled={trying || isDirty}
            title={isDirty ? '先儲存變更' : '啟動本機 connect-mode agent 測試'}
            className="border-border hover:bg-foreground/5 rounded-md border px-4 py-1.5 text-sm disabled:opacity-50"
          >
            {trying ? '啟動中…' : 'Try ▶'}
          </button>
        )}
      </div>
    </div>
  );
}
