import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const SESSION_COOKIE = 'admin_session';

async function makeSessionToken(password: string): Promise<string> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(password),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, encoder.encode('admin-authenticated'));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

// Constant-time string comparison. The Edge runtime doesn't expose
// crypto.subtle.timingSafeEqual, so we do a manual constant-time loop.
function timingSafeEqual(a: string, b: string): boolean {
  // Compare a fixed number of bytes to avoid leaking length differences.
  const len = Math.max(a.length, b.length);
  let mismatch = a.length ^ b.length;
  for (let i = 0; i < len; i++) {
    const ca = i < a.length ? a.charCodeAt(i) : 0;
    const cb = i < b.length ? b.charCodeAt(i) : 0;
    mismatch |= ca ^ cb;
  }
  return mismatch === 0;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const adminPassword = process.env.ADMIN_PASSWORD;

  if (!adminPassword) {
    // Production must always have ADMIN_PASSWORD set, otherwise the admin
    // surface (and /api/token, which mints LiveKit credentials) would be open
    // to anyone who can reach the deployment.
    if (process.env.NODE_ENV === 'production') {
      return new NextResponse(
        'ADMIN_PASSWORD is not configured. Refusing to serve admin routes in production.',
        { status: 503 }
      );
    }
    // Local dev without auth.
    return NextResponse.next();
  }

  // Login page is always accessible
  if (pathname === '/admin/login') return NextResponse.next();

  const cookie = request.cookies.get(SESSION_COOKIE)?.value ?? '';
  const expected = await makeSessionToken(adminPassword);

  if (!timingSafeEqual(cookie, expected)) {
    if (pathname.startsWith('/api/')) {
      return new NextResponse('Unauthorized', { status: 401 });
    }
    const loginUrl = new URL('/admin/login', request.url);
    loginUrl.searchParams.set('from', pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/admin/:path*', '/api/token'],
};
