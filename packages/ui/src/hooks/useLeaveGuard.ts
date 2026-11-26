import type { PendingVisit } from '@inertiajs/core';
import { router } from '@inertiajs/react';
import { type RefObject, useEffect } from 'react';

/**
 * Warn before leaving a page with unsaved changes.
 *
 * Uses window.confirm for Inertia visits and browser Back/Forward, plus the
 * browser's native unload warning. The page's own save must not be prompted
 * about, even though it is an Inertia visit too.
 *
 * @param dirty   Whether there is anything worth warning about.
 * @param message The confirm copy, already translated.
 * @param saving  Set by the page while it is driving its own save visit.
 * @param allowVisit Return true to skip the Inertia leave prompt for a visit
 *   that preserves unsaved fields. Does not bypass history or unload warnings.
 */
export function useLeaveGuard(
  dirty: boolean,
  message: string,
  saving: RefObject<boolean>,
  allowVisit?: (visit: PendingVisit) => boolean,
): void {
  useEffect(() => {
    if (!dirty) return;
    let currentUrl = window.location.href;
    let currentState = window.history.state;
    const rememberCurrentEntry = () => {
      currentUrl = window.location.href;
      currentState = window.history.state;
    };
    // Replacements don't fire navigate (e.g. settings module switches).
    const updates = ['inertia:navigate', 'inertia:finish', 'inertia:clientVisit'];
    for (const event of updates) document.addEventListener(event, rememberCurrentEntry);

    const guardHistory = (event: PopStateEvent) => {
      if (saving.current || window.confirm(message)) return;
      // Inertia v3 restores history in a bubble listener, without a cancellable
      // before event. Capture runs first, even when this hook mounts later.
      event.stopImmediatePropagation();
      window.history.pushState(currentState, '', currentUrl);
    };
    window.addEventListener('popstate', guardHistory, true);
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    const stopListening = router.on('before', ({ detail: { visit } }) =>
      visit.prefetch || saving.current || allowVisit?.(visit) ? true : window.confirm(message),
    );
    return () => {
      window.removeEventListener('popstate', guardHistory, true);
      for (const event of updates) document.removeEventListener(event, rememberCurrentEntry);
      window.removeEventListener('beforeunload', warn);
      stopListening();
    };
  }, [dirty, message, saving, allowVisit]);
}
