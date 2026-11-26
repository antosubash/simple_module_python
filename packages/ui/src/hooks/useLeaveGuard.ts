import type { PendingVisit } from '@inertiajs/core';
import { router } from '@inertiajs/react';
import { type RefObject, useEffect, useRef } from 'react';
import { trackLeaveGuardHistory } from './leaveGuardHistory';

let dirtyGuards = 0;
let originalScrollRestoration: History['scrollRestoration'];

/**
 * Warn before leaving a page with unsaved changes.
 *
 * `beforeunload` never fires for Inertia visits, including sidebar and Cancel
 * links, so those need a separate window.confirm prompt. Browser Back/Forward
 * restores history without Inertia's cancellable `before` event and needs its
 * own listener. Full page unloads use the browser's native warning instead.
 * Without the Navigation API, untracked entries (pre-mount or native null-state
 * hash entries) cannot be cancelled safely and are allowed without a prompt.
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
  const latest = useRef({ dirty, message, saving });
  latest.current = { dirty, message, saving };
  const approvedHistoryUrl = useRef<string | undefined>(undefined);
  useEffect(
    () =>
      trackLeaveGuardHistory((canCancel) => {
        approvedHistoryUrl.current = undefined;
        const { dirty, message, saving } = latest.current;
        if (!canCancel || !dirty || saving.current) return true;
        if (!window.confirm(message)) return false;
        approvedHistoryUrl.current = window.location.href;
        return true;
      }),
    [],
  );
  useEffect(() => {
    if (!dirty) return;
    const clearApproval = () => {
      approvedHistoryUrl.current = undefined;
    };
    const updates = ['inertia:navigate', 'inertia:clientVisit'];
    for (const event of updates) document.addEventListener(event, clearApproval);
    // Suppress native scroll restoration on the rejected and return traversals.
    if (dirtyGuards++ === 0) {
      originalScrollRestoration = window.history.scrollRestoration;
      window.history.scrollRestoration = 'manual';
    }
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    const stopListening = router.on('before', ({ detail: { visit } }) => {
      const approvedUrl = approvedHistoryUrl.current;
      if (!visit.prefetch) approvedHistoryUrl.current = undefined;
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
      clearApproval();
      if (--dirtyGuards === 0) window.history.scrollRestoration = originalScrollRestoration;
      for (const event of updates) document.removeEventListener(event, clearApproval);
      window.removeEventListener('beforeunload', warn);
      stopListening();
    };
  }, [dirty, message, saving, allowVisit]);
}
