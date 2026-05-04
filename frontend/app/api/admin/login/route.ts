import { NextResponse } from 'next/server';
import { SESSION_COOKIE, makeSessionToken, timingSafeEqual } from '@/lib/session';

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

  // Distinguish "client sent garbage" (400) from "wrong password" (401).
  // Folding both into 401 made client-side bugs masquerade as auth failures.
  let body: { password?: unknown };
  try {
    body = (await req.json()) as { password?: unknown };
  } catch {
    return new NextResponse('Invalid JSON body', { status: 400 });
  }
  // Use the same timing-safe compare we use for the cookie — partly defence
  // in depth (network jitter usually masks the timing leak on a per-request
  // RTT, but this is free and matches the middleware's pattern), partly
  // checkbox compliance for security audits.
  if (typeof body?.password !== 'string' || !timingSafeEqual(body.password, adminPassword)) {
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
