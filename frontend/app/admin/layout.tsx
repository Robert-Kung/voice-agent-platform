import type { ReactNode } from 'react';
import Link from 'next/link';
import { Toaster } from '@/components/ui/sonner';

export default function AdminLayout({ children }: { children: ReactNode }) {
  const navItems = [
    { href: '/admin/dashboard', label: 'Dashboard' },
    { href: '/admin/profiles', label: 'Profiles' },
    { href: '/admin/sessions', label: 'Sessions' },
  ];

  return (
    <div className="flex min-h-screen flex-col pt-20">
      <nav className="border-border border-b">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-4">
          <h1 className="font-mono text-sm font-bold tracking-wider uppercase">Agent Admin</h1>
          <div className="flex gap-4">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-foreground/80 hover:text-foreground text-sm transition-colors"
              >
                {item.label}
              </Link>
            ))}
          </div>
        </div>
      </nav>
      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">{children}</main>
      <Toaster position="top-right" richColors />
    </div>
  );
}
