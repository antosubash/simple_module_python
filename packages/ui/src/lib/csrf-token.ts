/**
 * The session's CSRF token as the client sees it: the `csrfToken` shared prop
 * the server sends to signed-in sessions (#504). Tracked from Inertia's
 * `navigate`/`success` events, with the page embedded in the document as the
 * fallback before the first event fires.
 */
import { router } from '@inertiajs/react';

let current: string | null = null;

function tokenOf(page: unknown): string | null {
  const value = (page as { props?: { csrfToken?: unknown } } | null)?.props?.csrfToken;
  return typeof value === 'string' && value ? value : null;
}

/** Override the tracked token (tests; a page that receives its own token prop). */
export function setCsrfToken(token: string | null): void {
  current = token;
}

/** The current page's `csrfToken`, or null when the server sent none (anonymous). */
export function currentCsrfToken(): string | null {
  if (current || typeof document === 'undefined') return current;
  const el = document.querySelector('script[data-page][type="application/json"]');
  try {
    return el?.textContent ? tokenOf(JSON.parse(el.textContent)) : null;
  } catch {
    return null;
  }
}

try {
  if (typeof window !== 'undefined' && typeof router?.on === 'function') {
    const track = (event: { detail: { page: unknown } }) => {
      current = tokenOf(event.detail.page);
    };
    router.on('navigate', track);
    router.on('success', track);
  }
} catch {
  // A test double of @inertiajs/react without `router`; the DOM fallback still works.
}
