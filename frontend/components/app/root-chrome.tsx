'use client';

import { usePathname } from 'next/navigation';

/**
 * Wraps root-layout decorations (header, theme toggle) that should
 * NOT appear on admin pages – the admin layout has its own sidebar
 * and controls.
 */
export function RootChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname?.startsWith('/admin')) return null;
  return <>{children}</>;
}
