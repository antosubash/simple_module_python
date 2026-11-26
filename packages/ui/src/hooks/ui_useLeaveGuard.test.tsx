/** Browser history traversal must preserve the live form when leaving is cancelled. */
import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { Harness, installHistory, saveFlag } from './leaveGuardHistoryTestUtils';
import type { useLeaveGuard } from './useLeaveGuard';

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

let history: ReturnType<typeof installHistory>;
let restore: ReturnType<typeof vi.fn>;
const state = (url: string) => ({ page: { url, props: { name: 'Saved' } } });
const settle = () => act(async () => {});

beforeEach(() => {
  history = installHistory();
  restore = vi.fn();
  // Installed before the hook, like Inertia's bubble listener.
  window.addEventListener('popstate', restore);
});
afterEach(() => window.removeEventListener('popstate', restore));

function edit(allowVisit?: Parameters<typeof useLeaveGuard>[3]) {
  const saving = saveFlag();
  const form = (dirty: boolean) => (
    <StrictMode>
      <Harness dirty={dirty} saving={saving} allowVisit={allowVisit} />
      <input aria-label="Name" defaultValue="Saved" />
    </StrictMode>
  );
  const view = render(form(false));
  window.history.replaceState(state('/a'), '', '/a');
  window.history.pushState(state('/b'), '', '/b');
  window.history.pushState(state('/c'), '', '/c');
  view.rerender(form(true));
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Draft' } });
  return { ...view, saving, clean: () => view.rerender(form(false)) };
}

function expectDraft() {
  expect(screen.getByRole('textbox')).toHaveValue('Draft');
  expect(restore).not.toHaveBeenCalled();
}

test.each([-1, -2])('cancel Back %s preserves the exact entry and entire stack', async (delta) => {
  edit();
  const entries = structuredClone(history.entries);
  const entry = history.entries[2];
  confirm.mockReturnValue(false);
  window.history.go(delta);
  await settle();
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(history.position).toBe(2);
  expect(history.entries).toEqual(entries);
  expect(history.entries[2]).toBe(entry);
  expect(window.location.pathname).toBe('/c');
  expect(window.history.scrollRestoration).toBe('manual');
  expectDraft();
});

test.each([false, true])('cancel Forward preserves A → B → C (allowVisit: %s)', async (allow) => {
  const allowVisit = vi.fn(() => true);
  edit(allow ? allowVisit : undefined);
  window.history.back();
  await settle();
  restore.mockClear();
  confirm.mockClear().mockReturnValue(false);
  const entries = structuredClone(history.entries);
  window.history.forward();
  await settle();
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(allowVisit).not.toHaveBeenCalled();
  expect(history.position).toBe(1);
  expect(history.entries).toEqual(entries);
  expect(window.location.pathname).toBe('/b');
  expectDraft();
});

test.each([undefined, 'inertia:finish', 'inertia:navigate', 'inertia:clientVisit'])(
  'cancel retains live remembered state and scroll after replaceState (%s)',
  async (event) => {
    edit();
    const live = {
      page: { ...state('/c?tab=mail').page, rememberedState: { form: { name: 'Draft' } } },
      documentScrollPosition: { top: 321, left: 12 },
      scrollRegions: [{ top: 99, left: 0 }],
    };
    window.history.replaceState(live, '', '/c?tab=mail');
    if (event) document.dispatchEvent(new CustomEvent(event));
    const entries = structuredClone(history.entries);
    confirm.mockReturnValue(false);
    window.history.back();
    await settle();
    expect(history.position).toBe(2);
    expect(history.entries).toEqual(entries);
    expect(window.history.state).toMatchObject(live);
    expect(window.location.search).toBe('?tab=mail');
    expectDraft();
  },
);

test('hash creation, Back and Forward never prompt, while a path change still does', async () => {
  edit();
  history.hash('#one');
  history.hash('#two');
  window.history.back();
  await settle();
  window.history.forward();
  await settle();
  expect(confirm).not.toHaveBeenCalled();
  expect(window.location.hash).toBe('#two');
  restore.mockClear();
  const entries = structuredClone(history.entries);
  confirm.mockReturnValue(false);
  window.history.go(-3);
  await settle();
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(history.position).toBe(4);
  expect(history.entries).toEqual(entries);
  expectDraft();
});

test('native null-state hashes use Navigation API positions without losing the draft', async () => {
  history.navigation();
  edit();
  history.hash('#one', null);
  history.hash('#two', null);
  window.history.back();
  await settle();
  window.history.forward();
  await settle();
  expect(confirm).not.toHaveBeenCalled();
  restore.mockClear();
  const entries = structuredClone(history.entries);
  confirm.mockReturnValue(false);
  window.history.go(-3);
  await settle();
  expect(history.position).toBe(4);
  expect(history.entries).toEqual(entries);
  expectDraft();
});

test.each(['clean', 'saving', 'unmount', 'confirm'])(
  '%s allows traversal normally',
  async (mode) => {
    window.history.scrollRestoration = 'auto';
    const push = window.history.pushState;
    const replace = window.history.replaceState;
    const view = edit();
    if (mode === 'clean') view.clean();
    if (mode === 'saving') view.saving.current = true;
    if (mode === 'unmount') view.unmount();
    const entries = structuredClone(history.entries);
    window.history.back();
    await settle();
    expect(history.position).toBe(1);
    expect(history.entries).toEqual(entries);
    expect(restore).toHaveBeenCalledTimes(1);
    expect(confirm).toHaveBeenCalledTimes(mode === 'confirm' ? 1 : 0);
    if (mode === 'clean' || mode === 'unmount') {
      expect(window.history.scrollRestoration).toBe('auto');
    }
    if (mode === 'unmount') {
      expect(window.history.pushState).toBe(push);
      expect(window.history.replaceState).toBe(replace);
    }
  },
);

test.each(['recovery', 'post', 'otherUrl'])(
  'approved refetch is one-use and scoped: %s',
  async (mode) => {
    edit();
    const before = handlers[handlers.length - 1];
    window.history.back();
    await settle();
    const visit = {
      prefetch: false,
      url: new URL(
        mode === 'otherUrl' ? '/unrelated' : window.location.href,
        window.location.origin,
      ),
      method: mode === 'post' ? 'post' : 'get',
      replace: true,
      preserveState: true,
      preserveScroll: true,
    };
    confirm.mockReturnValue(false);
    expect(before({ detail: { visit } })).toBe(mode === 'recovery');
    expect(confirm).toHaveBeenCalledTimes(mode === 'recovery' ? 1 : 2);
    expect(before({ detail: { visit } })).toBe(false);
  },
);

test('Navigation API positions let Cancel return from an entry predating the hook', async () => {
  history.navigation();
  window.history.pushState(state('/older'), '', '/older');
  edit();
  const entries = structuredClone(history.entries);
  confirm.mockReturnValue(false);
  window.history.go(-3);
  await settle();
  expect(history.position).toBe(3);
  expect(history.entries).toEqual(entries);
  expectDraft();
});

test('without a known target position, traversal is allowed without rewriting history', async () => {
  window.history.pushState(state('/older'), '', '/older');
  edit();
  const entries = structuredClone(history.entries);
  confirm.mockReturnValue(false);
  window.history.go(-3);
  await settle();
  expect(confirm).not.toHaveBeenCalled();
  expect(history.position).toBe(0);
  expect(history.entries).toEqual(entries);
  expect(restore).toHaveBeenCalledTimes(1);
});
