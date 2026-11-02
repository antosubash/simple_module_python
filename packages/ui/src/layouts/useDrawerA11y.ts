import { type RefObject, useEffect } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Tailwind's `lg` breakpoint, where SidebarLayout docks the sidebar
 * (`lg:translate-x-0`) and the drawer stops being a modal.
 */
export const DESKTOP_SIDEBAR_QUERY = '(min-width: 64rem)';

/** Rendered and reachable: `lg:hidden` items and `[hidden]`/`[inert]` subtrees are not. */
function isFocusable(el: HTMLElement): boolean {
  return !el.closest('[hidden], [inert]') && el.getClientRects().length > 0;
}

/**
 * Modal-dialog behaviour for the mobile sidebar drawer (WAI-ARIA dialog
 * pattern): Escape closes it, focus moves in on open and is trapped while it is
 * open, and focus returns to whatever opened it on close.
 *
 * The drawer element stays mounted (it is the static sidebar on desktop), so
 * this is a hook rather than a Dialog primitive. Crossing to the desktop
 * breakpoint closes the drawer, which releases the trap and drops the dialog
 * semantics the layout keys on `open`.
 */
export function useDrawerA11y(
  open: boolean,
  onClose: () => void,
  drawerRef: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    const desktop =
      typeof window.matchMedia === 'function' ? window.matchMedia(DESKTOP_SIDEBAR_QUERY) : null;
    const drawer = drawerRef.current;
    const updateVisibility = () => {
      const hidden = !open && !desktop?.matches;
      drawer?.toggleAttribute('inert', hidden);
      if (hidden) drawer?.setAttribute('aria-hidden', 'true');
      else drawer?.removeAttribute('aria-hidden');
    };
    updateVisibility();
    const onBreakpoint = (e: MediaQueryListEvent) => {
      updateVisibility();
      if (e.matches && open) onClose();
    };
    desktop?.addEventListener('change', onBreakpoint);
    const unsubscribe = () => desktop?.removeEventListener('change', onBreakpoint);
    if (!open) return unsubscribe;
    if (desktop?.matches) {
      onClose();
      return unsubscribe;
    }
    const opener = document.activeElement as HTMLElement | null;
    const items = () =>
      drawer ? Array.from(drawer.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(isFocusable) : [];
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
      unsubscribe();
      document.removeEventListener('keydown', onKeyDown);
      if (opener?.isConnected) opener.focus();
    };
  }, [open, onClose, drawerRef]);
}
