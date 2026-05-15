'use client';

import { type ReactNode, useState } from 'react';

interface CollapsibleSectionProps {
  title: string;
  icon?: ReactNode;
  badge?: ReactNode;
  defaultOpen?: boolean;
  id?: string;
  children: ReactNode;
}

/**
 * A collapsible section for the right panel in the profile editor v2.
 * Shows title + badge summary when collapsed; expands to show full content.
 */
export function CollapsibleSection({
  title,
  icon,
  badge,
  defaultOpen = false,
  id,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div id={id} className="border-border border-b last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="hover:bg-foreground/5 flex w-full items-center gap-2 px-4 py-3 text-left transition-colors"
      >
        <span className="text-foreground/50 w-4 shrink-0 text-xs">
          {open ? '▾' : '▸'}
        </span>
        {icon && <span className="text-foreground/60 shrink-0">{icon}</span>}
        <span className="text-foreground text-sm font-medium flex-1">{title}</span>
        {badge && !open && (
          <span className="text-foreground/50 text-xs">{badge}</span>
        )}
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}
