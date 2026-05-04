import { NextResponse } from 'next/server';
import { SESSION_COOKIE } from '@/lib/session';

export async function POST() {
  const res = NextResponse.json({ ok: true });
  // Match the path that login/route.ts sets (`/`). Without an explicit path,
  // some runtimes/browsers don't pair the deletion with the original cookie
  // and leave it in place — making logout silently no-op.
  res.cookies.delete({ name: SESSION_COOKIE, path: '/' });
  return res;
}
