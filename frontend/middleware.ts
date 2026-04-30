import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { SESSION_COOKIE, getExpectedSessionToken, timingSafeEqual } from '@/lib/session';

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

  // Login endpoints are always accessible — the page itself, and the API
  // route the form posts to. Everything else under /api/admin/* is gated.
  if (pathname === '/admin/login' || pathname === '/api/admin/login') {
    return NextResponse.next();
  }

  const cookie = request.cookies.get(SESSION_COOKIE)?.value ?? '';
  const expected = await getExpectedSessionToken(adminPassword);

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
  matcher: [
    '/admin/:path*',
    '/api/token',
    // Auth-management endpoints — login is bypassed inside the handler.
    '/api/admin/:path*',
    // Server-side proxy to the FastAPI admin API. Without this gate, the
    // proxy would forward unauthenticated browser calls to the backend.
    '/api/admin-proxy/:path*',
  ],
};
