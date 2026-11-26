import { createRef } from 'react';
import { vi } from 'vitest';
import { useLeaveGuard } from './useLeaveGuard';

export const MESSAGE = 'You have unsaved changes.';

export function Harness({
  dirty,
  saving,
  allowVisit,
}: {
  dirty: boolean;
  saving: { current: boolean };
  allowVisit?: Parameters<typeof useLeaveGuard>[3];
}) {
  useLeaveGuard(dirty, MESSAGE, saving, allowVisit);
  return null;
}

export function saveFlag(value = false) {
  const ref = createRef<boolean>() as { current: boolean };
  ref.current = value;
  return ref;
}

// Deterministic same-document history: go is asynchronous, push truncates the
// forward stack, and replace overwrites the whole state just as Inertia does.
export function installHistory() {
  const replace = window.history.replaceState.bind(window.history);
  const entries = [{ state: null as unknown, url: new URL('/initial', location.href).href }];
  let position = 0;
  replace(null, '', '/initial');
  const show = () => replace(entries[position].state, '', entries[position].url);
  const go = (delta = 0) => {
    queueMicrotask(() => {
      const target = position + delta;
      if (!delta || target < 0 || target >= entries.length) return;
      position = target;
      show();
      window.dispatchEvent(new PopStateEvent('popstate', { state: entries[position].state }));
    });
  };
  vi.spyOn(window.history, 'go').mockImplementation(go);
  vi.spyOn(window.history, 'back').mockImplementation(() => go(-1));
  vi.spyOn(window.history, 'forward').mockImplementation(() => go(1));
  const push: History['pushState'] = (state, _, url) => {
    entries.splice(++position, entries.length, {
      state: structuredClone(state),
      url: new URL(url ?? window.location.href, window.location.href).href,
    });
    show();
  };
  vi.spyOn(window.history, 'pushState').mockImplementation(push);
  vi.spyOn(window.history, 'replaceState').mockImplementation((state, _, url) => {
    entries[position] = {
      state: structuredClone(state),
      url: new URL(url ?? window.location.href, window.location.href).href,
    };
    show();
  });
  return {
    entries,
    get position() {
      return position;
    },
    // Native hash navigation copies state, then emits popstate/hashchange.
    hash(hash: string, state: unknown = window.history.state) {
      const oldURL = window.location.href;
      push(state, '', hash);
      window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
      window.dispatchEvent(
        new HashChangeEvent('hashchange', { oldURL, newURL: window.location.href }),
      );
    },
    navigation() {
      vi.stubGlobal('navigation', {
        get currentEntry() {
          return { index: position };
        },
      });
    },
  };
}
