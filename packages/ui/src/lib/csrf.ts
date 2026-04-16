/**
 * CSRF token helpers for non-Inertia fetch() calls.
 *
 * Inertia visits route through the ``router.on('before', ...)`` hook in
 * ``host/client_app/app.tsx`` and are handled there. Anything that uses raw
 * ``fetch()`` (e.g. login, forgot-password, admin mutations) must use
 * ``fetchWithCsrf`` instead so the server-side CSRFMiddleware accepts the
 * request.
 *
 * The token is session-scoped on the server (see ``CSRFMiddleware``) and
 * arrives in the Inertia shared props as ``csrf_token`` on every response.
 * ``app.tsx`` calls ``setCsrfToken`` on boot and after each navigation to
 * keep this module's copy fresh.
 */

let csrfToken = '';

export function setCsrfToken(token: string): void {
  csrfToken = token;
}

export function getCsrfToken(): string {
  return csrfToken;
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

export function fetchWithCsrf(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? 'GET').toUpperCase();
  if (SAFE_METHODS.has(method)) {
    return fetch(input, init);
  }
  const headers = new Headers(init?.headers);
  if (csrfToken && !headers.has('X-CSRF-Token')) {
    headers.set('X-CSRF-Token', csrfToken);
  }
  return fetch(input, { ...init, headers });
}
