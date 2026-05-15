'use client';

import { type ReactNode } from 'react';

interface ProfileEditorLayoutProps {
  header: ReactNode;
  center: ReactNode;
  rightPanel: ReactNode;
}

/**
 * Split-panel layout for the v2 profile editor.
 * Left/center: 60% — Prompt editing area (always visible)
 * Right: 40% — Collapsible config sections + Flow minimap
 */
export function ProfileEditorLayout({ header, center, rightPanel }: ProfileEditorLayoutProps) {
  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col overflow-hidden">
      {/* Sticky header */}
      <div className="border-border bg-background/95 shrink-0 border-b backdrop-blur">{header}</div>

      {/* Main content area — split panel */}
      <div className="flex min-h-0 flex-1">
        {/* Center: Prompt area */}
        <div className="border-border flex min-h-0 flex-[3] flex-col overflow-y-auto border-r">
          <div className="flex-1 p-6">{center}</div>
        </div>

        {/* Right panel: Config sections */}
        <div className="flex min-h-0 flex-[2] flex-col overflow-y-auto">
          <div className="p-4">{rightPanel}</div>
        </div>
      </div>
    </div>
  );
}
