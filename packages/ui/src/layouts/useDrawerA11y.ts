import { type RefObject, useEffect } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Modal-dialog behaviour for the mobile sidebar drawer (WAI-ARIA dialog
 * pattern): Escape closes it, focus moves in on open and is trapped while it is
 * open, and focus returns to whatever opened it on close.
 *
 * The drawer element stays mounted (it is the static sidebar on desktop), so
 * this is a hook rather than a Dialog primitive.
 */
export function useDrawerA11y(
  open: boolean,
  onClose: () => void,
  drawerRef: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!open) return;
    const drawer = drawerRef.current;
    const opener = document.activeElement as HTMLElement | null;
    const items = () => (drawer ? Array.from(drawer.querySelectorAll<HTMLElement>(FOCUSABLE)) : []);
    items()[0]?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        // A nested menu (user dropdown) owns its own Escape.
        if (e.defaultPrevented || (e.target as HTMLElement | null)?.closest?.('[role="menu"]')) {
          return;
        }
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== 'Tab' || !drawer) return;
      const list = items();
      if (list.length === 0) return;
      const first = list[0];
      const last = list[list.length - 1];
      const active = document.activeElement;
      if (!drawer.contains(active)) {
        // Focus escaped (e.g. clicked the backdrop): pull it back in.
        e.preventDefault();
        first.focus();
      } else if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      if (opener?.isConnected) opener.focus();
    };
  }, [open, onClose, drawerRef]);
}
