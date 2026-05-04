// Shared admin session token primitives.
//
// Both the login route (which sets the cookie) and the middleware (which
// validates it on every admin request) must compute the same value from the
// same password. Keeping them in one module means a change to the algorithm,
// message, or cookie name updates both sides at once — accidental drift would
// silently break login.

export const SESSION_COOKIE = 'admin_session';

// HMAC message — included so the signature isn't a raw HMAC of the password
// alone. Bumping this string invalidates every existing session.
const SESSION_MESSAGE = 'admin-authenticated';

export async function makeSessionToken(password: string): Promise<string> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(password),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, encoder.encode(SESSION_MESSAGE));
  return btoa(String.fromCharCode(...new Uint8Array(sig)));
}

// Memoised wrapper for the hot path: middleware runs on every matched request
// and ADMIN_PASSWORD doesn't change at runtime, so re-running HMAC each time
// is wasted CPU. Cache is invalidated automatically if the password value ever
// differs (e.g. password rotation followed by an in-place env reload).
let _expectedTokenCache: { password: string; promise: Promise<string> } | null = null;

export function getExpectedSessionToken(password: string): Promise<string> {
  if (_expectedTokenCache?.password !== password) {
    _expectedTokenCache = { password, promise: makeSessionToken(password) };
  }
  return _expectedTokenCache.promise;
}

// Constant-time string comparison. The Edge runtime doesn't expose
// crypto.subtle.timingSafeEqual, so we do a manual constant-time loop.
export function timingSafeEqual(a: string, b: string): boolean {
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
