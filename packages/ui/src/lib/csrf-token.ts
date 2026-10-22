/**
 * The session's CSRF token as the client sees it: the `csrfToken` shared prop
 * the server sends to signed-in sessions (#504). Tracked from Inertia's
 * `navigate`/`success` events, with the page embedded in the document as the
 * fallback before the first event fires.
 */
import { router } from '@inertiajs/react';

// undefined = no page event seen yet (use the embedded page); null = page has no token.
let current: string | null | undefined;
// The document's embedded page never changes: parse it once per distinct text.
let embedded: { text: string; token: string | null } | null = null;

function tokenOf(page: unknown): string | null {
  const value = (page as { props?: { csrfToken?: unknown } } | null)?.props?.csrfToken;
  return typeof value === 'string' && value ? value : null;
}

/** Override the tracked token (tests; a page that receives its own token prop). `undefined` re-enables the embedded-page fallback. */
export function setCsrfToken(token: string | null | undefined): void {
  current = token;
}

/** The current page's `csrfToken`, or null when the server sent none (anonymous). */
export function currentCsrfToken(): string | null {
  if (current !== undefined) return current;
  if (typeof document === 'undefined') return null;
  const text = document.querySelector('script[data-page][type="application/json"]')?.textContent;
  if (!text) return null;
  if (embedded?.text !== text) {
    try {
      embedded = { text, token: tokenOf(JSON.parse(text)) };
    } catch {
      embedded = { text, token: null };
    }
  }
  return embedded.token;
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
