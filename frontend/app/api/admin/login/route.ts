import { NextResponse } from 'next/server';
import { SESSION_COOKIE, makeSessionToken } from '@/lib/session';

// True when the inbound request reached us over HTTPS — either directly or
// through a TLS-terminating reverse proxy that set X-Forwarded-Proto. We tie
// the Secure cookie flag to this rather than NODE_ENV so prod builds running
// on HTTP localhost (e.g. `docker compose up` for testing) still log in.
function requestIsHttps(req: Request): boolean {
  if (new URL(req.url).protocol === 'https:') return true;
  return req.headers.get('x-forwarded-proto') === 'https';
}

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
    secure: requestIsHttps(req),
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 7,
    path: '/',
  });
  return res;
}
