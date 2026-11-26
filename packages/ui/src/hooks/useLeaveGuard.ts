import type { PendingVisit } from '@inertiajs/core';
import { router } from '@inertiajs/react';
import { type RefObject, useEffect } from 'react';

/**
 * Warn before leaving a page with unsaved changes.
 *
 * `beforeunload` never fires for Inertia visits, including sidebar and Cancel
 * links, so those need a separate window.confirm prompt. Browser Back/Forward
 * restores history without Inertia's cancellable `before` event and needs its
 * own listener. Full page unloads use the browser's native warning instead.
 * The page's own save must not trigger the Inertia or history prompt.
 *
 * @param dirty   Whether there is anything worth warning about.
 * @param message The confirm copy, already translated.
 * @param saving  Set during the page's own save; skips Inertia/history prompts,
 *   but not the browser's unload warning.
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
    let approvedHistoryUrl: string | undefined;
    const rememberCurrentEntry = (event: Event) => {
      currentUrl = window.location.href;
      currentState = window.history.state;
      if (event.type !== 'inertia:finish') approvedHistoryUrl = undefined;
    };
    // Replacements don't fire navigate (e.g. settings module switches).
    const updates = ['inertia:navigate', 'inertia:finish', 'inertia:clientVisit'];
    for (const event of updates) document.addEventListener(event, rememberCurrentEntry);

    const guardHistory = (event: PopStateEvent) => {
      approvedHistoryUrl = undefined;
      if (saving.current) return;
      if (window.confirm(message)) {
        approvedHistoryUrl = window.location.href;
        return;
      }
      // Inertia v3 restores history in a bubble listener, without a cancellable
      // before event. Capture runs first, even when this hook mounts later.
      event.stopImmediatePropagation();
      window.history.pushState(currentState, '', currentUrl);
    };
    window.addEventListener('popstate', guardHistory, true);
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    const stopListening = router.on('before', ({ detail: { visit } }) => {
      const approvedUrl = approvedHistoryUrl;
      if (!visit.prefetch) approvedHistoryUrl = undefined;
      if (visit.prefetch || saving.current || allowVisit?.(visit)) return true;
      // Inertia refetches invalid/old history entries after the popstate approval.
      const recoveringHistory =
        approvedUrl !== undefined &&
        approvedUrl === visit.url.href &&
        visit.method === 'get' &&
        visit.replace &&
        visit.preserveState === true &&
        visit.preserveScroll === true;
      return recoveringHistory || window.confirm(message);
    });
    return () => {
      window.removeEventListener('popstate', guardHistory, true);
      for (const event of updates) document.removeEventListener(event, rememberCurrentEntry);
      window.removeEventListener('beforeunload', warn);
      stopListening();
    };
  }, [dirty, message, saving, allowVisit]);
}
