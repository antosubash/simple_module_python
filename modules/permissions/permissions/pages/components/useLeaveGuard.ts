import { router } from '@inertiajs/react';
import { type RefObject, useEffect } from 'react';

/**
 * Warn before leaving a page with unsaved changes.
 *
 * `beforeunload` alone is not enough: it never fires for an Inertia visit, and
 * "Cancel" and every sidebar link are Inertia visits — i.e. every ordinary way
 * of leaving. Ported from `users/pages/Users/Edit.tsx`, including its escape
 * hatch: the page's own save is a visit too, and must not be prompted about.
 *
 * @param dirty   Whether there is anything worth warning about.
 * @param message The confirm copy, already translated.
 * @param saving  Set by the page while it is driving its own save visit.
 */
export function useLeaveGuard(dirty: boolean, message: string, saving: RefObject<boolean>): void {
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    const stopListening = router.on('before', () =>
      saving.current ? true : window.confirm(message),
    );
    return () => {
      window.removeEventListener('beforeunload', warn);
      stopListening();
    };
  }, [dirty, message, saving]);
}
