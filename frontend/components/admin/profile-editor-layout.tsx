'use client';

import { useEffect, type ReactNode } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { X } from 'lucide-react';

interface ProfileEditorLayoutProps {
  header: ReactNode;
  center: ReactNode;
  rightPanel: ReactNode;
  panelOpen?: boolean;
  onPanelClose?: () => void;
}

/**
 * Split-panel layout for the v2 profile editor.
 * md+: Left/center 60% | Right 40% always visible
 * <md: Right panel becomes a slide-in drawer triggered from the header
 */
export function ProfileEditorLayout({
  header,
  center,
  rightPanel,
  panelOpen,
  onPanelClose,
}: ProfileEditorLayoutProps) {
  useEffect(() => {
    if (!panelOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onPanelClose?.();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [panelOpen, onPanelClose]);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col overflow-hidden">
      {/* Sticky header */}
      <div className="border-border bg-background/95 shrink-0 border-b backdrop-blur">{header}</div>

      {/* Main content area — split panel */}
      <div className="flex min-h-0 flex-1">
        {/* Center: Prompt area */}
        <div className="border-border flex min-h-0 flex-1 flex-col overflow-y-auto md:flex-[3] md:border-r">
          <div className="flex-1 p-6">{center}</div>
        </div>

        {/* Right panel — desktop only (md+) */}
        <div className="hidden min-h-0 flex-[2] flex-col overflow-y-auto md:flex">
          <div className="p-4">{rightPanel}</div>
        </div>
      </div>

      {/* Mobile drawer (< md) */}
      <AnimatePresence>
        {panelOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              className="bg-black/40 fixed inset-0 z-40 md:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={onPanelClose}
            />
            {/* Drawer */}
            <motion.div
              className="bg-background fixed inset-y-0 right-0 z-50 flex w-80 max-w-[85vw] flex-col shadow-xl md:hidden"
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
            >
              <div className="border-border flex shrink-0 items-center justify-between border-b px-4 py-3">
                <span className="text-sm font-medium">Settings</span>
                <button
                  type="button"
                  onClick={onPanelClose}
                  className="text-foreground/50 hover:text-foreground rounded p-1"
                >
                  <X size={16} />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto">{rightPanel}</div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
