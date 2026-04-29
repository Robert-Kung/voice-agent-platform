// Server-side proxy from /api/admin-proxy/* → ADMIN_API_URL/*.
//
// Architecture: the browser is authenticated via the ADMIN_PASSWORD session
// cookie (validated by middleware.ts). The FastAPI backend is authenticated
// independently via the X-Admin-Token header. This proxy is the bridge:
//
//   Browser  ──cookie──▶  Next.js middleware  ──cookie ok──▶  this proxy
//                                                                   │
//                                                       inject X-Admin-Token
//                                                                   ▼
//                                                          FastAPI /api/*
//
// ADMIN_API_TOKEN never reaches the browser bundle — it's read from
// process.env at request time and only attached server-side.
//
// Adding a new admin-only API endpoint is just:
//   1. Add the route in api/routes_*.py with `require_admin`
//   2. Call it from frontend/lib/admin-api.ts using the same path under
//      `/api/admin-proxy/...`
// No new proxy file needed.
import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

// Hop-by-hop headers from the inbound request that we don't want to forward
// (or that fetch will set itself). 'host' would point at the Next.js server,
// not FastAPI; 'content-length' is recomputed by the runtime.
const STRIP_REQUEST_HEADERS = new Set([
  'host',
  'connection',
  'content-length',
  'transfer-encoding',
  // Don't trust browser-supplied tokens — we set it ourselves.
  'x-admin-token',
]);

// Headers from the upstream response we don't want to forward back.
const STRIP_RESPONSE_HEADERS = new Set([
  'connection',
  'transfer-encoding',
  'content-encoding', // fetch already decoded; re-emitting would double-encode
  'content-length', // let the runtime recompute
]);

function getAdminApiUrl(): string | null {
  return process.env.ADMIN_API_URL || process.env.NEXT_PUBLIC_ADMIN_API_URL || null;
}

async function forward(req: NextRequest, pathSegments: string[]): Promise<Response> {
  const apiUrl = getAdminApiUrl();
  if (!apiUrl) {
    return NextResponse.json(
      { error: 'ADMIN_API_URL is not configured on the server' },
      { status: 500 }
    );
  }

  const incoming = new URL(req.url);
  const target = `${apiUrl.replace(/\/+$/, '')}/${pathSegments.join('/')}${incoming.search}`;

  const outboundHeaders = new Headers();
  req.headers.forEach((value, key) => {
    if (!STRIP_REQUEST_HEADERS.has(key.toLowerCase())) {
      outboundHeaders.set(key, value);
    }
  });

  const adminToken = process.env.ADMIN_API_TOKEN;
  if (adminToken) {
    outboundHeaders.set('X-Admin-Token', adminToken);
  }

  // Pass through the body for verbs that have one. Use arrayBuffer so binary
  // payloads (rare here, but possible) survive intact.
  const hasBody = !['GET', 'HEAD'].includes(req.method);
  const body = hasBody ? await req.arrayBuffer() : undefined;

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers: outboundHeaders,
      body,
      cache: 'no-store',
      redirect: 'manual',
    });
  } catch (err) {
    return NextResponse.json(
      { error: `Upstream fetch failed: ${(err as Error).message}` },
      { status: 502 }
    );
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!STRIP_RESPONSE_HEADERS.has(key.toLowerCase())) {
      responseHeaders.set(key, value);
    }
  });

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

type RouteContext = { params: Promise<{ path: string[] }> };

async function handler(req: NextRequest, ctx: RouteContext): Promise<Response> {
  const { path } = await ctx.params;
  return forward(req, path ?? []);
}

export { handler as GET, handler as POST, handler as PUT, handler as PATCH, handler as DELETE };
