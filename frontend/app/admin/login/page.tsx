'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';

function safeRedirect(from: string | null): string {
  // Only allow same-origin admin paths. Reject protocol-relative URLs (//evil.com),
  // absolute URLs (https://evil.com), and any non-/admin/ paths.
  if (!from) return '/admin/dashboard';
  if (!from.startsWith('/admin/')) return '/admin/dashboard';
  if (from.includes('//')) return '/admin/dashboard';
  if (from.includes('\\')) return '/admin/dashboard';
  return from;
}

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const from = safeRedirect(searchParams.get('from'));

  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');

    const res = await fetch('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });

    if (res.ok) {
      router.replace(from);
    } else {
      setError('密碼錯誤');
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <form onSubmit={handleSubmit} className="flex w-80 flex-col gap-4">
        <h1 className="font-mono text-lg font-bold">Agent Admin</h1>
        <input
          type="password"
          placeholder="Admin password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="border-border bg-background rounded-md border px-3 py-2 text-sm outline-none focus:ring-2"
          autoFocus
        />
        {error && <p className="text-destructive text-sm">{error}</p>}
        <Button type="submit" disabled={loading || !password}>
          {loading ? '驗證中...' : '登入'}
        </Button>
      </form>
    </div>
  );
}
