const POSITION = '__simpleModuleLeaveGuard';

// crypto.randomUUID exists only in secure contexts; a plain-HTTP deployment
// must not crash, and the group only has to differ between mounts.
const newGroup = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

type NavigationWindow = Window & { navigation?: { currentEntry?: { index: number } } };

/** Track while mounted, including clean renders, so later dirty traversals can return exactly. */
export function trackLeaveGuardHistory(approve: (canCancel: boolean) => boolean) {
  const history = window.history;
  const push = history.pushState;
  const replace = history.replaceState;
  let group = newGroup();
  let index: number | undefined = 0;
  let currentUrl = window.location.href;
  let returning = false;
  let disposed = false;
  const navigationIndex = () => (window as NavigationWindow).navigation?.currentEntry?.index;
  const readIndex = (state: unknown): number | undefined => {
    const position = state && typeof state === 'object' && POSITION in state && state[POSITION];
    if (position && typeof position === 'object' && 'group' in position && 'index' in position) {
      if (
        position.group === group &&
        typeof position.index === 'number' &&
        Number.isSafeInteger(position.index)
      ) {
        return position.index;
      }
    }
    return undefined;
  };
  const stamp = (state: unknown, position: number) => ({
    ...(state && typeof state === 'object' ? state : {}),
    [POSITION]: { group, index: position },
  });
  replace.call(history, stamp(history.state, index), '');
  index = navigationIndex() ?? index;

  const ensureIndex = () => {
    if (index === undefined) {
      // A traversal crossed the observed segment; don't reuse its coordinates.
      group = newGroup();
      index = 0;
    }
    return index;
  };
  const wrappedReplace: History['replaceState'] = function (this: History, state, title, url) {
    // Inertia replaces the entire object for remember/scroll, without events.
    replace.call(this, stamp(state, ensureIndex()), title, url);
    currentUrl = window.location.href;
  };
  const wrappedPush: History['pushState'] = function (this: History, state, title, url) {
    const next = ensureIndex() + 1;
    push.call(this, stamp(state, next), title, url);
    index = navigationIndex() ?? next;
    currentUrl = window.location.href;
  };
  history.replaceState = wrappedReplace;
  history.pushState = wrappedPush;

  const guard = (event: PopStateEvent) => {
    if (returning) {
      returning = false;
      event.stopImmediatePropagation();
      if (disposed) window.removeEventListener('popstate', guard, true);
      return;
    }
    const url = new URL(window.location.href);
    const previous = new URL(currentUrl);
    const hashOnly =
      url.href !== previous.href &&
      url.origin === previous.origin &&
      url.pathname === previous.pathname &&
      url.search === previous.search;
    let target = navigationIndex() ?? readIndex(event.state);
    if (hashOnly) {
      // Some hash entries copy their predecessor's state, including its index.
      if (target === index && index !== undefined) {
        target = index + 1;
        replace.call(history, stamp(history.state, target), '');
      }
      // Inertia would otherwise remount a remembered page for a hash traversal.
      event.stopImmediatePropagation();
    }
    const delta = index !== undefined && target !== undefined ? index - target : 0;
    if (!approve(!hashOnly && delta !== 0)) {
      // Capture precedes Inertia's bubble listener. Neither it nor the return
      // traversal may restore a page or scroll over the live unsaved form.
      event.stopImmediatePropagation();
      returning = true;
      history.go(delta);
      return;
    }
    // shortcut: untracked entries (pre-mount or native null-state hashes) have
    // no known distance without Navigation API; allow rather than guess.
    index = target;
    currentUrl = url.href;
  };
  window.addEventListener('popstate', guard, true);
  return () => {
    disposed = true;
    // A return already queued must stay hidden from Inertia even after unmount.
    if (!returning) window.removeEventListener('popstate', guard, true);
    if (history.replaceState === wrappedReplace) history.replaceState = replace;
    if (history.pushState === wrappedPush) history.pushState = push;
  };
}
