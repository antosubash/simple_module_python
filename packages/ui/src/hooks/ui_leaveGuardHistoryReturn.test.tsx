/** Rejected history traversals must return to the live entry, even with queued user input. */
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { Harness, installHistory, saveFlag } from './leaveGuardHistoryTestUtils';

vi.mock('@inertiajs/react', () => ({ router: { on: () => () => {} } }));

let history: ReturnType<typeof installHistory>;
let confirm: ReturnType<typeof vi.fn>;
let restore: ReturnType<typeof vi.fn>;
// Returns correct after a short quiet period; advance past it without real waits.
const settle = () => act(() => vi.advanceTimersByTimeAsync(200));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  history = installHistory();
  confirm = vi.fn(() => false);
  vi.stubGlobal('confirm', confirm);
  restore = vi.fn();
  window.addEventListener('popstate', restore);
});

afterEach(() => {
  cleanup();
  window.removeEventListener('popstate', restore);
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function edit() {
  const view = render(
    <>
      <Harness dirty={true} saving={saveFlag()} />
      <input aria-label="Name" defaultValue="Draft" />
    </>,
  );
  window.history.replaceState({ page: 'a' }, '', '/a');
  for (const page of ['b', 'c', 'd']) window.history.pushState({ page }, '', `/${page}`);
  return view;
}

test.each([false, true])(
  'three queued rejected Backs retain the live D entry (Navigation API: %s)',
  async (navigation) => {
    if (navigation) history.navigation();
    edit();
    const entries = structuredClone(history.entries);
    window.history.back();
    window.history.back();
    window.history.back();
    await settle();
    expect(history.position).toBe(3);
    expect(window.location.pathname).toBe('/d');
    expect(history.entries).toEqual(entries);
    expect(screen.getByRole('textbox')).toHaveValue('Draft');
    expect(restore).not.toHaveBeenCalled();
    expect(confirm).toHaveBeenCalledTimes(1);
  },
);

test.each([false, true])(
  'queued rejected Backs with Forward history settle on the live entry (Navigation API: %s)',
  async (navigation) => {
    if (navigation) history.navigation();
    render(
      <>
        <Harness dirty={true} saving={saveFlag()} />
        <input aria-label="Name" defaultValue="Draft" />
      </>,
    );
    window.history.replaceState({ page: 'a' }, '', '/a');
    for (const page of ['b', 'c', 'd', 'e', 'f', 'g']) {
      window.history.pushState({ page }, '', `/${page}`);
    }
    confirm.mockImplementation(() => true);
    window.history.go(-3);
    await settle();
    expect(window.location.pathname).toBe('/d');
    restore.mockClear();
    confirm.mockImplementation(() => false);
    window.history.back();
    window.history.back();
    await settle();
    expect(window.location.pathname).toBe('/d');
    expect(restore).not.toHaveBeenCalled();
  },
);

test.each(['before', 'after'])(
  'a missing return releases its capture listener when unmounted %s expiry',
  async (unmount) => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const remove = vi.spyOn(window, 'removeEventListener');
    const view = edit();
    // An out-of-range go() produces no popstate at all.
    vi.mocked(window.history.go).mockImplementation(() => {});
    window.history.back();
    await settle();
    expect(confirm).toHaveBeenCalledTimes(1);
    if (unmount === 'before') view.unmount();
    vi.runAllTimers();
    if (unmount === 'after') view.unmount();
    try {
      expect(remove.mock.calls.some(([type, , capture]) => type === 'popstate' && capture)).toBe(
        true,
      );
      window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
      expect(restore).toHaveBeenCalledTimes(1);
    } finally {
      // Release the old implementation's leaked listener even when this regression fails.
      window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
    }
  },
);

test('an unknown return position is allowed through without another prompt', async () => {
  edit();
  confirm.mockImplementation(() => {
    history.entries[3].state = null;
    return false;
  });
  window.history.back();
  await settle();
  expect(history.position).toBe(3);
  expect(restore).toHaveBeenCalledTimes(1);
  expect(confirm).toHaveBeenCalledTimes(1);
});

test('a copied position at a different URL is not mistaken for the live entry', async () => {
  edit();
  confirm.mockImplementation(() => {
    // A cached original pushState can copy coordinates onto an unobserved entry.
    history.entries[3].url = new URL('/foreign', location.href).href;
    return false;
  });
  window.history.back();
  await settle();
  expect(window.location.pathname).toBe('/foreign');
  expect(restore).toHaveBeenCalledTimes(1);
  expect(window.history.go).toHaveBeenCalledTimes(1);
  expect(confirm).toHaveBeenCalledTimes(1);
});

test('return corrections are bounded and leave the form dirty-guarded on fallback', async () => {
  edit();
  vi.mocked(window.history.go).mockImplementation(() => {
    queueMicrotask(() =>
      window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state })),
    );
  });
  window.history.back();
  await settle();
  expect(restore).toHaveBeenCalledTimes(1);
  expect(vi.mocked(window.history.go).mock.calls.length).toBeLessThanOrEqual(8);
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('textbox')).toHaveValue('Draft');
  const unload = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(unload);
  expect(unload.defaultPrevented).toBe(true);
});
