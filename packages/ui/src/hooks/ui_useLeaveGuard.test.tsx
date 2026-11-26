/**
 * The unsaved-changes guard both page suites stub out.
 *
 * `UserEdit.test.tsx` and its sibling mock `router` as `{ on: () => () => {} }`,
 * so the prompt and its escape hatch were never exercised — and the escape
 * hatch is the load-bearing half: the page's own save is an Inertia visit too,
 * and prompting on it would ask "discard your changes?" while saving them.
 */
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createRef } from 'react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

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

const { useLeaveGuard } = await import('./useLeaveGuard');

const MESSAGE = 'You have unsaved changes.';

function Harness({
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

function saveFlag(value = false) {
  const ref = createRef<boolean>() as { current: boolean };
  ref.current = value;
  return ref;
}

let confirm: ReturnType<typeof vi.fn>;

beforeEach(() => {
  handlers.length = 0;
  stopListening.mockClear();
  confirm = vi.fn(() => true);
  vi.stubGlobal('confirm', confirm);
});

afterEach(() => {
  cleanup();
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

describe('browser history', () => {
  const editState = { page: { url: '/edit', props: { name: 'Saved' } } };
  const otherState = { page: { url: '/other', props: {} } };
  let restore: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // Inertia installs a bubble listener before the page mounts. A restore
    // replaces the page, so an uncontrolled input's draft disappears too.
    restore = vi.fn(() => cleanup());
    window.addEventListener('popstate', restore);
    window.history.replaceState(otherState, '', '/other');
    window.history.pushState(editState, '', '/edit');
  });

  afterEach(() => window.removeEventListener('popstate', restore));

  function edit(dirty = true) {
    const view = render(
      <>
        <Harness dirty={dirty} saving={saveFlag()} />
        <input aria-label="Name" defaultValue="Saved" />
      </>,
    );
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Draft' } });
    return view;
  }

  test('dirty Back prompts before restoration; cancel keeps the URL, state and draft', async () => {
    edit();
    confirm.mockReturnValue(false);
    window.history.back();

    await waitFor(() => expect(confirm).toHaveBeenCalledWith(MESSAGE));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(restore).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe('/edit');
    expect(window.history.state).toEqual(editState);
    expect(screen.getByRole('textbox')).toHaveValue('Draft');
  });

  test('confirming Back proceeds with one prompt', async () => {
    edit();
    window.history.back();

    await waitFor(() => expect(restore).toHaveBeenCalledTimes(1));
    expect(confirm).toHaveBeenCalledWith(MESSAGE);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(window.location.pathname).toBe('/other');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  test('clean Back proceeds without prompting or adding history entries', async () => {
    edit(false);
    const length = window.history.length;
    window.history.back();

    await waitFor(() => expect(restore).toHaveBeenCalledTimes(1));
    expect(confirm).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe('/other');
    expect(window.history.length).toBe(length);
  });

  test('dirty Forward prompts and can be cancelled', async () => {
    window.history.back();
    await waitFor(() => expect(restore).toHaveBeenCalledTimes(1));
    restore.mockClear();
    edit();
    confirm.mockReturnValue(false);
    window.history.forward();

    await waitFor(() => expect(confirm).toHaveBeenCalledWith(MESSAGE));
    expect(restore).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe('/other');
    expect(window.history.state).toEqual(otherState);
    expect(screen.getByRole('textbox')).toHaveValue('Draft');
  });

  test.each(['inertia:finish', 'inertia:navigate', 'inertia:clientVisit'])(
    'cancel restores the latest entry after %s, including replacements',
    async (event) => {
      edit();
      const updated = { page: { url: '/edit?module=mail', props: { name: 'Updated' } } };
      window.history.replaceState(updated, '', '/edit?module=mail');
      document.dispatchEvent(new CustomEvent(event));
      confirm.mockReturnValue(false);
      window.history.back();

      await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
      expect(window.location.pathname + window.location.search).toBe('/edit?module=mail');
      expect(window.history.state).toEqual(updated);
      expect(screen.getByRole('textbox')).toHaveValue('Draft');
      expect(restore).not.toHaveBeenCalled();
    },
  );

  test('saving bypasses the history prompt too', async () => {
    render(<Harness dirty={true} saving={saveFlag(true)} />);
    window.history.back();

    await waitFor(() => expect(restore).toHaveBeenCalledTimes(1));
    expect(confirm).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe('/other');
  });

  test.each(['clean', 'unmount'])(
    '%s removes the history guard without trapping Back',
    async (action) => {
      const view = edit();
      if (action === 'clean') view.rerender(<Harness dirty={false} saving={saveFlag()} />);
      else view.unmount();
      window.history.back();

      await waitFor(() => expect(restore).toHaveBeenCalledTimes(1));
      expect(confirm).not.toHaveBeenCalled();
      expect(window.location.pathname).toBe('/other');
    },
  );
});
