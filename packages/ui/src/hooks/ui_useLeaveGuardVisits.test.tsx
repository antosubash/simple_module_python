/** Inertia visits and full-page unloads must warn without interrupting the page's own save. */
import '@testing-library/jest-dom/vitest';
import { cleanup, render } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { Harness, installHistory, MESSAGE, saveFlag } from './leaveGuardHistoryTestUtils';

const handlers: Array<(event: { detail: { visit: { prefetch: boolean } } }) => boolean> = [];
const stopListening = vi.fn();

vi.mock('@inertiajs/react', () => ({
  router: {
    on: (
      _event: string,
      handler: (event: { detail: { visit: { prefetch: boolean } } }) => boolean,
    ) => {
      handlers.push(handler);
      return stopListening;
    },
  },
}));

let confirm: ReturnType<typeof vi.fn>;

beforeEach(() => {
  handlers.length = 0;
  stopListening.mockClear();
  confirm = vi.fn(() => true);
  vi.stubGlobal('confirm', confirm);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('while there is nothing to lose', () => {
  test('it registers nothing at all', () => {
    render(<Harness dirty={false} saving={saveFlag()} />);

    expect(handlers).toHaveLength(0);
  });
});

describe('with unsaved changes', () => {
  test('leaving asks first, and the answer decides', () => {
    render(<Harness dirty={true} saving={saveFlag()} />);

    expect(handlers).toHaveLength(1);
    expect(handlers[0]({ detail: { visit: { prefetch: false } } })).toBe(true);
    expect(confirm).toHaveBeenCalledWith(MESSAGE);

    confirm.mockReturnValue(false);
    expect(handlers[0]({ detail: { visit: { prefetch: false } } })).toBe(false);
  });

  test("the page's own save is not prompted about", () => {
    // The escape hatch. Saving is an Inertia visit like any other, so without
    // this the guard interrupts the very action that resolves it.
    render(<Harness dirty={true} saving={saveFlag(true)} />);

    expect(handlers[0]({ detail: { visit: { prefetch: false } } })).toBe(true);
    expect(confirm).not.toHaveBeenCalled();
  });

  test('it stops listening when the changes are gone', () => {
    const { rerender } = render(<Harness dirty={true} saving={saveFlag()} />);
    expect(stopListening).not.toHaveBeenCalled();

    rerender(<Harness dirty={false} saving={saveFlag()} />);
    expect(stopListening).toHaveBeenCalled();
  });

  test('it stops listening on unmount', () => {
    const { unmount } = render(<Harness dirty={true} saving={saveFlag()} />);
    unmount();

    expect(stopListening).toHaveBeenCalled();
  });
});

describe('the browser-level guard', () => {
  test('a full page unload is cancelled too, since Inertia never sees it', () => {
    render(<Harness dirty={true} saving={saveFlag()} />);

    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  test('and is not cancelled when there is nothing to lose', () => {
    render(<Harness dirty={false} saving={saveFlag()} />);

    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});

test('prefetching while dirty never prompts or blocks', () => {
  render(<Harness dirty={true} saving={saveFlag()} />);
  confirm.mockReturnValue(false);
  expect(handlers[0]({ detail: { visit: { prefetch: true } } })).toBe(true);
  expect(confirm).not.toHaveBeenCalled();
});

test('allowVisit still exempts only matching link visits', () => {
  const allowVisit = vi.fn(() => true);
  render(<Harness dirty={true} saving={saveFlag()} allowVisit={allowVisit} />);
  confirm.mockReturnValue(false);
  expect(handlers[0]({ detail: { visit: { prefetch: false } } })).toBe(true);
  expect(confirm).not.toHaveBeenCalled();
  allowVisit.mockReturnValue(false);
  expect(handlers[0]({ detail: { visit: { prefetch: false } } })).toBe(false);
  expect(confirm).toHaveBeenCalledWith(MESSAGE);
});

test('a dirty guard still blocks Back when an earlier guard is clean', async () => {
  const history = installHistory();
  render(<Harness dirty={false} saving={saveFlag()} />);
  render(<Harness dirty={true} saving={saveFlag()} />);
  window.history.pushState({ page: 'a' }, '', '/a');
  window.history.pushState({ page: 'b' }, '', '/b');
  confirm.mockReturnValue(false);
  window.history.back();
  await Promise.resolve();
  await Promise.resolve();
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(history.position).toBe(2);
  expect(window.location.pathname).toBe('/b');
});

test.each([0, 1])('history wrappers are released in unmount order %s', (first) => {
  installHistory();
  const push = window.history.pushState;
  const replace = window.history.replaceState;
  const views = [
    render(<Harness dirty={false} saving={saveFlag()} />),
    render(<Harness dirty={false} saving={saveFlag()} />),
  ];
  views[first].unmount();
  views[1 - first].unmount();
  expect(window.history.pushState).toBe(push);
  expect(window.history.replaceState).toBe(replace);
});

test.each([0, 1])('scroll restoration lasts until the final dirty guard: %s', (first) => {
  window.history.scrollRestoration = 'auto';
  const views = [
    render(<Harness dirty={true} saving={saveFlag()} />),
    render(<Harness dirty={true} saving={saveFlag()} />),
  ];
  views[first].unmount();
  expect(window.history.scrollRestoration).toBe('manual');
  views[1 - first].unmount();
  expect(window.history.scrollRestoration).toBe('auto');
});

test.each([{ state: null }, { state: ['value'] }, { state: new Date('2026-01-01') }])(
  'other libraries retain non-record history state: %j',
  ({ state }) => {
    installHistory();
    render(<Harness dirty={false} saving={saveFlag()} />);
    window.history.pushState(state, '', '/other');
    expect(window.history.state).toEqual(state);
    window.history.replaceState(state, '', '/other');
    expect(window.history.state).toEqual(state);
  },
);

test('a later library wrapper survives cleanup and no longer stamps guard state', () => {
  installHistory();
  const view = render(<Harness dirty={false} saving={saveFlag()} />);
  const push = window.history.pushState;
  const replace = window.history.replaceState;
  const foreignPush: History['pushState'] = (state, title, url) =>
    push.call(window.history, state, title, url);
  const foreignReplace: History['replaceState'] = (state, title, url) =>
    replace.call(window.history, state, title, url);
  window.history.pushState = foreignPush;
  window.history.replaceState = foreignReplace;
  try {
    view.unmount();
    expect(window.history.pushState).toBe(foreignPush);
    expect(window.history.replaceState).toBe(foreignReplace);
    window.history.pushState({ owner: 'library' }, '', '/other');
    expect(window.history.state).toEqual({ owner: 'library' });
    window.history.replaceState({ owner: 'library' }, '', '/other');
    expect(window.history.state).toEqual({ owner: 'library' });
  } finally {
    window.history.pushState = push;
    window.history.replaceState = replace;
  }
});

test('SSR renders the hook without accessing window', () => {
  vi.stubGlobal('window', undefined);
  expect(renderToString(<Harness dirty={true} saving={saveFlag()} />)).toBe('');
});

test('an event at the current entry never calls go(0)', () => {
  installHistory();
  render(<Harness dirty={true} saving={saveFlag()} />);
  window.history.replaceState({ page: 'current' }, '', '/current');
  confirm.mockReturnValue(false);
  window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  expect(confirm).not.toHaveBeenCalled();
  expect(window.history.go).not.toHaveBeenCalled();
});

test('a queued remember write during Cancel does not relabel the rejected entry', async () => {
  const history = installHistory();
  render(<Harness dirty={true} saving={saveFlag()} />);
  window.history.replaceState({ page: 'a' }, '', '/a');
  window.history.pushState({ page: 'b' }, '', '/b');
  window.history.pushState({ page: 'c' }, '', '/c');
  confirm.mockReturnValue(false).mockImplementationOnce(() => {
    queueMicrotask(() => window.history.replaceState({ page: 'b', remembered: 'draft' }, ''));
    return false;
  });
  window.history.back();
  await Promise.resolve();
  await Promise.resolve();
  expect(history.position).toBe(2);
  window.history.back();
  await Promise.resolve();
  await Promise.resolve();
  expect(confirm).toHaveBeenCalledTimes(2);
  expect(history.position).toBe(2);
});
