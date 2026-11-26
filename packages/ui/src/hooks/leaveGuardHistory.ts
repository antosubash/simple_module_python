// Quiet period before correcting a return that queued user traversals overtook.
const SETTLE_MS = 50;
const POSITION = '__simpleModuleLeaveGuard';

// crypto.randomUUID exists only in secure contexts; a plain-HTTP deployment
// must not crash, and the group only has to differ between mounts.
const newGroup = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

type NavigationWindow = Window & { navigation?: { currentEntry?: { index: number } } };
type Approve = (canCancel: boolean) => boolean;
const guards = new Set<{ approve: Approve }>();
let stopTracking: (() => void) | undefined;

/** Track while mounted, including clean renders, so later dirty traversals can return exactly. */
export function trackLeaveGuardHistory(approve: Approve) {
  const registration = { approve };
  // All guards share coordinates and one capture listener, regardless of unmount order.
  stopTracking ??= observeHistory((canCancel) =>
    [...guards].every((guard) => guard.approve(canCancel)),
  );
  guards.add(registration);
  return () => {
    if (!guards.delete(registration)) return;
    if (guards.size === 0) {
      stopTracking?.();
      stopTracking = undefined;
    }
  };
}

function observeHistory(approve: Approve) {
  const history = window.history;
  const push = history.pushState;
  const replace = history.replaceState;
  let group = newGroup();
  let index: number | undefined = 0;
  let currentUrl = window.location.href;
  let returning: { position: number; navigation: boolean; attempts: number } | undefined;
  let returnTimer: ReturnType<typeof setTimeout> | undefined;
  let settleTimer: ReturnType<typeof setTimeout> | undefined;
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
  const stamp = (state: unknown, position: number) => {
    // Preserve other libraries' null, primitive, array and built-in state values.
    if (
      !state ||
      typeof state !== 'object' ||
      (Object.getPrototypeOf(state) !== Object.prototype && Object.getPrototypeOf(state) !== null)
    ) {
      return state;
    }
    return { ...state, [POSITION]: { group, index: position } };
  };
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
    if (disposed) return replace.call(this, state, title, url);
    if (returning) {
      // Queued remember/scroll writes still belong to the rejected entry until go returns.
      const target = navigationIndex() ?? readIndex(history.state);
      return replace.call(this, target === undefined ? state : stamp(state, target), title, url);
    }
    // Inertia replaces the entire object for remember/scroll, without events.
    replace.call(this, stamp(state, ensureIndex()), title, url);
    currentUrl = window.location.href;
  };
  const wrappedPush: History['pushState'] = function (this: History, state, title, url) {
    if (disposed) return push.call(this, state, title, url);
    const next = ensureIndex() + 1;
    push.call(this, stamp(state, next), title, url);
    index = navigationIndex() ?? next;
    currentUrl = window.location.href;
  };
  // Cached pre-wrapper pushState calls bypass tracking; Inertia 3.11 reads it
  // dynamically. Unknown/inconsistent positions fall back to allowing traversal.
  history.replaceState = wrappedReplace;
  history.pushState = wrappedPush;

  const finishReturn = () => {
    returning = undefined;
    clearTimeout(returnTimer);
    clearTimeout(settleTimer);
    returnTimer = undefined;
    settleTimer = undefined;
    if (disposed) window.removeEventListener('popstate', guard, true);
  };
  const returnToLive = (actual: number) => {
    if (!returning) return;
    returning.attempts++;
    clearTimeout(returnTimer);
    // Out-of-range go() is silent. Expire even if the last guard unmounted.
    returnTimer = setTimeout(() => {
      finishReturn();
      index = undefined;
      currentUrl = window.location.href;
    }, 1000);
    history.go(returning.position - actual);
  };
  const guard = (event: PopStateEvent) => {
    const url = new URL(window.location.href);
    const navigation = navigationIndex();
    let target = navigation ?? readIndex(event.state);
    if (returning) {
      const actual = returning.navigation ? navigation : readIndex(event.state);
      if (actual === returning.position && url.href === currentUrl) {
        finishReturn();
        event.stopImmediatePropagation();
        return;
      }
      if (actual !== undefined && actual !== returning.position && returning.attempts < 5) {
        // More Back/Forward presses may precede the requested return popstate.
        // Correct once they settle: a relative go() per event would overshoot
        // while earlier traversals are still queued.
        event.stopImmediatePropagation();
        clearTimeout(settleTimer);
        settleTimer = setTimeout(() => {
          if (!returning) return;
          const now = returning.navigation ? navigationIndex() : readIndex(window.history.state);
          if (now === returning.position) finishReturn();
          else if (now !== undefined) returnToLive(now);
        }, SETTLE_MS);
        return;
      }
      // Unknown, aliased or repeatedly inconsistent positions cannot be undone safely.
      finishReturn();
      index = undefined;
      currentUrl = url.href;
      return;
    }
    const previous = new URL(currentUrl);
    const hashOnly =
      url.href !== previous.href &&
      url.origin === previous.origin &&
      url.pathname === previous.pathname &&
      url.search === previous.search;
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
    if (!approve(!hashOnly && delta !== 0) && index !== undefined && target !== undefined) {
      // Capture precedes Inertia's bubble listener. Neither it nor the return
      // traversal may restore a page or scroll over the live unsaved form.
      event.stopImmediatePropagation();
      returning = { position: index, navigation: navigation !== undefined, attempts: 0 };
      returnToLive(target);
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
