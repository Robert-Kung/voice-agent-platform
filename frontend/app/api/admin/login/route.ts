import { NextResponse } from 'next/server';
import { SESSION_COOKIE, makeSessionToken } from '@/lib/session';

export async function POST(req: Request) {
  const adminPassword = process.env.ADMIN_PASSWORD;
  if (!adminPassword) {
    return new NextResponse('ADMIN_PASSWORD not configured', { status: 500 });
  }

  const body = await req.json().catch(() => ({}));
  if (!body?.password || body.password !== adminPassword) {
    return new NextResponse('Invalid password', { status: 401 });
  }

  const token = await makeSessionToken(adminPassword);
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 7,
    path: '/',
  });
  return res;
}
