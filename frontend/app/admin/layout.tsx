'use client';

import type { ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { AdminSidebar } from '@/components/admin/sidebar';
import { Toaster } from '@/components/ui/sonner';

export default function AdminLayout({ children }: { children: ReactNode }) {
  const router = useRouter();

  async function handleLogout() {
    await fetch('/api/admin/logout', { method: 'POST' });
    router.replace('/admin/login');
  }

  return (
    <div className="admin-shell flex h-screen overflow-hidden">
      <AdminSidebar onLogout={handleLogout} />
      <div className="flex min-w-0 flex-1 flex-col">
        <main className="flex-1 overflow-y-auto p-6 lg:p-8">{children}</main>
      </div>
      <Toaster position="top-right" richColors />
    </div>
  );
}
